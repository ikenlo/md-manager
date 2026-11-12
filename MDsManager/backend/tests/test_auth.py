from datetime import timedelta

from sqlalchemy import select

from app.models import UserSession
from app.models.base import utcnow
from app.services.auth import hash_token


def test_login_and_me(client):
    r = client.post("/api/auth/login", json={"email": "admin@mds.local", "password": "admin"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["display_name"] == "Директор"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200 and me.json()["email"] == "admin@mds.local"


def test_token_stored_hashed(client, db_session):
    token = client.post(
        "/api/auth/login", json={"email": "admin@mds.local", "password": "admin"}
    ).json()["token"]
    sess = db_session.scalar(select(UserSession))
    assert sess.token_hash == hash_token(token) != token
    ttl = sess.expires_at - utcnow()
    assert timedelta(days=6, hours=23) < ttl <= timedelta(days=7)


def test_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "admin@mds.local", "password": "nope"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer bad"}).status_code == 401


def test_expired_session(client, db_session, auth):
    sess = db_session.scalar(select(UserSession))
    sess.expires_at = utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert client.get("/api/auth/me", headers=auth).status_code == 401


def test_logout(client, auth):
    assert client.post("/api/auth/logout", headers=auth).status_code == 204
    assert client.get("/api/auth/me", headers=auth).status_code == 401


def test_cors_preflight(client):
    r = client.options(
        "/api/auth/login",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_set_password_changes_login_and_revokes_sessions(client, db_session, auth):
    from app.set_password import set_password

    assert set_password(db_session, "admin@mds.local", "new-long-password")
    assert client.get("/api/auth/me", headers=auth).status_code == 401
    bad = client.post("/api/auth/login", json={"email": "admin@mds.local", "password": "admin"})
    assert bad.status_code == 401
    ok = client.post(
        "/api/auth/login", json={"email": "admin@mds.local", "password": "new-long-password"}
    )
    assert ok.status_code == 200
    assert not set_password(db_session, "nobody@mds.local", "x" * 12)
