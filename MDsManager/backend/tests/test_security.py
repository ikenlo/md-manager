import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import get_db
from app.services import cookies

LOGIN = "/api/auth/login"
GOOD = {"email": "admin@mds.local", "password": "admin"}
BAD = {"email": "admin@mds.local", "password": "wrong"}


@pytest.fixture
def make_app(monkeypatch, db_session):
    """Новий застосунок з іншими змінними оточення."""

    def build(**env):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        from app.main import create_app

        app = create_app()
        app.dependency_overrides[get_db] = lambda: db_session
        return app

    yield build
    get_settings.cache_clear()


# --- ліміт входу ---


def test_login_rate_limited_after_5_attempts(client):
    for _ in range(5):
        assert client.post(LOGIN, json=BAD).status_code == 401
    r = client.post(LOGIN, json=GOOD)
    assert r.status_code == 429
    assert r.headers["retry-after"] == "900"
    assert "Забагато" in r.json()["detail"]


def test_rate_limit_is_per_real_ip_behind_tunnel(make_app):
    # TestClient приходить з адреси "testclient" — робимо її довіреним проксі (як cloudflared)
    app = make_app(TRUSTED_PROXIES="testclient")
    with TestClient(app, base_url="http://localhost") as c:
        for _ in range(5):
            c.post(LOGIN, json=BAD, headers={"CF-Connecting-IP": "203.0.113.1"})
        blocked = c.post(LOGIN, json=GOOD, headers={"CF-Connecting-IP": "203.0.113.1"})
        other = c.post(LOGIN, json=GOOD, headers={"CF-Connecting-IP": "203.0.113.2"})
    assert blocked.status_code == 429
    assert other.status_code == 200


def test_spoofed_cf_header_ignored_from_untrusted_peer(client):
    # Не від проксі: різні CF-Connecting-IP не дають обійти ліміт
    for i in range(5):
        client.post(LOGIN, json=BAD, headers={"CF-Connecting-IP": f"198.51.100.{i}"})
    r = client.post(LOGIN, json=GOOD, headers={"CF-Connecting-IP": "198.51.100.99"})
    assert r.status_code == 429


def test_rate_limit_only_on_login(client, auth):
    for _ in range(10):
        assert client.get("/api/auth/me", headers=auth).status_code == 200


# --- TrustedHost ---


def test_unknown_host_rejected(client):
    r = client.get("/api/health", headers={"Host": "evil.example.com"})
    assert r.status_code == 400


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "localhost:8000"])
def test_local_hosts_allowed(client, host):
    assert client.get("/api/health", headers={"Host": host}).status_code == 200


def test_production_domain_allowed(make_app):
    app = make_app(ALLOWED_HOSTS="manager.example.com")
    with TestClient(app, base_url="http://manager.example.com") as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/health", headers={"Host": "other.example.com"}).status_code == 400


# --- HTTPS ---


def test_development_allows_http(client):
    assert client.get("/api/health").status_code == 200


def test_production_redirects_http(make_app):
    app = make_app(APP_ENV="production", ALLOWED_HOSTS="manager.example.com")
    with TestClient(app, base_url="http://manager.example.com") as c:
        r = c.get("/api/health?x=1", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["location"] == "https://manager.example.com/api/health?x=1"


def test_production_https_via_tunnel_not_redirected(make_app):
    app = make_app(
        APP_ENV="production", ALLOWED_HOSTS="manager.example.com", TRUSTED_PROXIES="testclient"
    )
    with TestClient(app, base_url="http://manager.example.com") as c:
        r = c.get("/api/health", headers={"X-Forwarded-Proto": "https"}, follow_redirects=False)
    assert r.status_code == 200


def test_production_forwarded_proto_ignored_from_untrusted_peer(make_app):
    app = make_app(APP_ENV="production", ALLOWED_HOSTS="manager.example.com")
    with TestClient(app, base_url="http://manager.example.com") as c:
        r = c.get("/api/health", headers={"X-Forwarded-Proto": "https"}, follow_redirects=False)
    assert r.status_code == 308


def test_production_localhost_not_redirected(make_app):
    app = make_app(APP_ENV="production", ALLOWED_HOSTS="manager.example.com")
    with TestClient(app, base_url="http://localhost") as c:
        assert c.get("/api/health", follow_redirects=False).status_code == 200


def test_production_hides_docs(make_app):
    app = make_app(APP_ENV="production", ALLOWED_HOSTS="manager.example.com")
    with TestClient(app, base_url="https://manager.example.com") as c:
        # 404 або index.html SPA (якщо frontend зібрано) — головне, без Swagger і схеми
        docs, schema = c.get("/docs"), c.get("/openapi.json")
    assert "swagger" not in docs.text.lower()
    assert '"openapi"' not in schema.text


# --- cookie ---


@pytest.mark.parametrize("env,secure", [("development", False), ("production", True)])
def test_session_cookie_flags(monkeypatch, env, secure):
    monkeypatch.setenv("APP_ENV", env)
    get_settings.cache_clear()
    try:
        from fastapi import Response

        resp = Response()
        cookies.set_session_cookie(resp, "tok")
        header = resp.headers["set-cookie"].lower()
        assert "httponly" in header and "samesite=lax" in header
        assert ("secure" in header) is secure
    finally:
        get_settings.cache_clear()
