"""Веб-застосунок MDS Manager: вхід через MDS Connect, ролі, огляд, контент, погодження, журнал."""

import json
import time
from datetime import UTC, date, datetime

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.ai import analyst as an
from app.ai.jobs import Background
from app.analytics import daily, dashboard
from app.config import Settings
from app.core import approvals
from app.db.models import AiReport, AuditLog, ContentItem
from app.web import api as web_api
from app.web import session as sess
from app.web import static as web_static
from tests.test_ai_analyst import REPORT, FakeAnthropic, FakeMds, make_analyst, seed_social
from tests.test_content import add_item, jpeg, make

NOW = datetime(2026, 11, 20, 6, 0, tzinfo=UTC)
MDS = "https://mds.example"


class FakeMdsAuth:
    """MDS Connect /api/auth/*: користувачі з ролями й двофакторним входом для admin2."""

    USERS = {
        "margaryta": {
            "id": 1,
            "username": "margaryta",
            "full_name": "Маргарита",
            "role": "director",
        },
        "olena": {"id": 2, "username": "olena", "full_name": "Олена", "role": "admin"},
        "admin2": {"id": 4, "username": "admin2", "full_name": "Ірина", "role": "admin"},
        "dmytro": {"id": 3, "username": "dmytro", "full_name": "Дмитро", "role": "master"},
    }

    def __init__(self):
        self.requests = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        self.requests.append((req.url.path, body))
        if req.url.path == "/api/auth/login":
            u = self.USERS.get(body["username"])
            if u is None or body["password"] != "pass":
                return httpx.Response(401, json={"detail": "Невірний логін або пароль"})
            if body["username"] == "admin2" and body.get("device_token") != "dev-1":
                return httpx.Response(
                    200, json={"twofa": True, "challenge_id": 7, "expires_in": 300}
                )
            return httpx.Response(200, json={"token": "mds-token", "user": u})
        if req.url.path == "/api/auth/login/verify":
            if body["code"] != "123456":
                return httpx.Response(401, json={"detail": "Невірний код"})
            return httpx.Response(200, json={"token": "t", "user": self.USERS["admin2"],
                                             "device_token": "dev-1"})  # fmt: skip
        return httpx.Response(404)


def build(engine, media, *, mds=True, claude_steps=(), **kw):
    st_settings = Settings(_env_file=None, anthropic_api_key="k", gemini_api_key="g",
                           panel_password="" if mds else "local-pass",
                           mds_url=MDS if mds else "", session_secret="s" * 32, **kw)  # fmt: skip
    studio, _ = make(engine, media)
    studio.settings = st_settings
    analyst = make_analyst(engine, FakeAnthropic(*claude_steps))
    fake_mds = FakeMdsAuth()

    async def dash():
        return await dashboard.build(engine, st_settings, NOW, mds=FakeMds())

    async def day():
        return await daily.build(engine, st_settings, NOW, mds=FakeMds())

    ctx = web_api.Ctx(
        settings=lambda: st_settings, engine=lambda: engine, studio=lambda: studio,
        jobs=Background(), hub=an.Hub(analyst), dashboard=dash, day=day,
        mds_http=httpx.AsyncClient(transport=httpx.MockTransport(fake_mds)),
        clock=lambda: datetime(2026, 12, 2, 8, tzinfo=UTC),
    )  # fmt: skip
    app = FastAPI()
    app.include_router(web_api.build_router(ctx))
    web_static.mount(app)
    c = TestClient(app, base_url="https://testserver")
    c.ctx, c.studio, c.fake_mds = ctx, studio, fake_mds
    return c


def login(c, user="margaryta", password="pass"):
    r = c.post("/api/auth/login", json={"username": user, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def wait(c):
    for _ in range(300):
        if not c.ctx.jobs.running and not c.ctx.hub.running:
            return
        time.sleep(0.01)
    raise AssertionError(c.ctx.jobs.running)


@pytest.fixture
def media(tmp_path):
    from app.content.storage import Media

    return Media(tmp_path / "media")


# --- сторінка й вхід ------------------------------------------------------------


def test_index_and_old_panel_redirect(engine, media):
    c = build(engine, media)
    r = c.get("/")
    assert r.status_code == 200 and "<title>MDS Manager</title>" in r.text
    assert f"app.js?v={__version__}" in r.text and "__V__" not in r.text
    assert c.get("/static/style.css").status_code == 200
    r = c.get("/panel/content?m=2026-12", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/"


def test_login_with_mds_roles(engine, media):
    c = build(engine, media)
    assert c.get("/api/me").status_code == 401
    r = c.post("/api/auth/login", json={"username": "margaryta", "password": "bad"})
    assert r.status_code == 401 and r.json()["detail"] == "Невірний логін або пароль"
    me = login(c)["user"]
    assert (me["name"], me["role"], me["role_name"]) == ("Маргарита", "owner", "Директор")
    assert "money" in me["perms"] and "settings" in me["perms"]
    cookie = c.cookies[sess.COOKIE]
    assert "mds-token" not in cookie  # токен MDS не зберігаємо
    assert c.get("/api/me").json()["mds_url"] == MDS
    c.post("/api/auth/logout")
    c.cookies.clear()
    assert c.get("/api/me").status_code == 401

    adm = login(c, "olena")["user"]
    assert adm["role"] == "admin" and set(adm["perms"]) == {"overview", "content", "dialogs"}
    c.cookies.clear()
    r = c.post("/api/auth/login", json={"username": "dmytro", "password": "pass"})
    assert r.status_code == 403 and "Майстри працюють у MDS Connect" in r.json()["detail"]


def test_login_two_factor(engine, media):
    c = build(engine, media)
    r = c.post("/api/auth/login", json={"username": "admin2", "password": "pass"})
    assert r.json() == {"twofa": True, "challenge_id": 7, "expires_in": 300}
    assert sess.COOKIE not in c.cookies
    bad = c.post("/api/auth/verify", json={"challenge_id": 7, "code": "000000"})
    assert bad.status_code == 401
    ok = c.post("/api/auth/verify", json={"challenge_id": 7, "code": "123456", "remember": True})
    assert ok.json()["device_token"] == "dev-1" and ok.json()["user"]["name"] == "Ірина"
    c.cookies.clear()
    r = c.post("/api/auth/login", json={"username": "admin2", "password": "pass",
                                        "device_token": "dev-1"})  # fmt: skip
    assert r.json()["user"]["role"] == "admin"  # запамʼятований пристрій — без коду


def test_local_password_without_mds(engine, media):
    c = build(engine, media, mds=False)
    assert c.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    assert login(c, "", "local-pass")["user"]["role"] == "owner"


def test_forged_or_expired_session(engine, media):
    c = build(engine, media)
    s = c.ctx.settings()
    c.cookies.set(sess.COOKIE, sess.issue(s, sess.Principal(1, "X", "owner")) + "0")
    assert c.get("/api/me").status_code == 401
    other = s.model_copy(update={"session_secret": "z" * 32})
    c.cookies.set(sess.COOKIE, sess.issue(other, sess.Principal(1, "X", "owner")))
    assert c.get("/api/me").status_code == 401
    expired = s.model_copy(update={"session_days": -1})
    c.cookies.set(sess.COOKIE, sess.issue(expired, sess.Principal(1, "X", "owner")))
    assert c.get("/api/me").status_code == 401


# --- огляд і права ---------------------------------------------------------------


def test_owner_overview_full(engine, media):
    seed_social(engine)
    with Session(engine) as s, s.begin():
        s.add(AiReport(kind="daily", period_start=date(2026, 11, 19), model="claude-opus-5-5",
                       cost_usd=0.12, payload=json.dumps(REPORT, ensure_ascii=False)))  # fmt: skip
    c = build(engine, media)
    login(c)
    d = c.get("/api/overview").json()
    groups = {g["key"]: g for g in d["day"]["groups"]}
    assert {"salon", "instagram", "facebook", "meta_ads", "google_ads"} <= set(groups)
    assert any(r["key"] == "revenue" for r in groups["salon"]["rows"])
    assert d["report"]["summary"].startswith("Вчора") and d["ads"] and d["posts"]
    assert d["period"]["revenue_kop"] > 0 and "ai_month" in d and d["approvals_pending"] == 0


def test_admin_sees_no_money(engine, media):
    seed_social(engine)
    c = build(engine, media)
    login(c, "olena")
    d = c.get("/api/overview").json()
    keys = {g["key"] for g in d["day"]["groups"]}
    assert "meta_ads" not in keys and "google_ads" not in keys
    salon = next(g for g in d["day"]["groups"] if g["key"] == "salon")
    assert "revenue" not in {r["key"] for r in salon["rows"]}
    for k in ("period", "ads", "sources", "ai_month", "report", "approvals_pending"):
        assert k not in d
    for path in ("/api/settings", "/api/audit", "/api/approvals"):
        assert c.get(path).status_code == 403
    assert c.post("/api/overview/report").status_code == 403
    assert c.get("/api/content").status_code == 200  # контент адміністраторам доступний


def test_run_daily_report(engine, media):
    from tests.test_ai_analyst import message

    with build(engine, media, claude_steps=[message(REPORT)]) as c:
        login(c)
        assert c.post("/api/overview/report").json() == {"ok": True}
        wait(c)
        assert c.get("/api/overview").json()["report"]["summary"].startswith("Вчора")


# --- контент-план -------------------------------------------------------------------


def test_content_flow_with_audit(engine, media):
    with build(engine, media) as c:
        login(c)
        d = c.get("/api/content?month=2026-12").json()
        assert (d["month"], d["posts"], d["stories"], d["missing"]) == ("2026-12", 5, 16, 21)
        assert d["can_write"] and d["can_edit_photos"] and d["max_rejections"] == 3

        files = [("files", ("a.jpg", jpeg(), "image/jpeg")), ("files", ("b.txt", b"x", "text/x"))]
        r = c.post("/api/content/photos", files=files)
        assert len(r.json()["added"]) == 1 and "b.txt" in r.json()["errors"][0]
        pid = r.json()["added"][0]
        iid = add_item(engine)
        assert c.post(f"/api/content/items/{iid}/approve").json() == {"ok": True}
        assert c.post(f"/api/content/items/{iid}/approve").status_code == 409
        c.post(f"/api/content/items/{iid}/photo", json={"photo_id": pid})
        wait(c)
        item = next(
            i for i in c.get("/api/content?month=2026-12").json()["items"] if i["id"] == iid
        )
        assert item["image_status"] == "ready" and item["image"]
        c.post(f"/api/content/items/{iid}/image-approve")
        item = next(
            i for i in c.get("/api/content?month=2026-12").json()["items"] if i["id"] == iid
        )
        assert item["status"] == "ready"
        r = c.get(f"/api/content/media/{item['image']}?download=1")
        assert (
            r.headers["content-type"] == "image/jpeg"
            and "attachment" in r.headers["content-disposition"]
        )
        assert c.get("/api/content/media/..%2Fsecret").status_code == 404
        assert c.post(f"/api/content/items/{iid}/unknown").status_code == 404
        c.post(f"/api/content/items/{iid}/published")
        assert c.delete(f"/api/content/photos/{pid}").status_code == 409  # фото в готовому пості
    with Session(engine) as s:
        acts = [a.action for a in s.scalars(select(AuditLog).order_by(AuditLog.id))]
        actor = s.scalar(select(AuditLog.actor).where(AuditLog.action == "content.approve"))
    assert acts[:2] == ["auth.login", "content.photos"]
    assert {
        "content.approve",
        "content.photo",
        "content.image-approve",
        "content.published",
    } <= set(acts)
    assert actor == "Маргарита (директор)"


def test_reject_via_api_runs_rework(engine, media):
    from tests.test_ai_analyst import message
    from tests.test_content import idea

    with build(engine, media) as c:
        c.studio.claude.responses.append(message(idea(topic="Новий кут")))
        login(c, "olena")
        iid = add_item(engine)
        c.post(f"/api/content/items/{iid}/reject", json={"reason": "Задовгий текст"})
        wait(c)
        item = c.get("/api/content?month=2026-12").json()["items"][0]
    assert item["topic"] == "Новий кут" and item["rejections"] == 1
    assert "Задовгий текст" in c.studio.claude.requests[0]["messages"][0]["content"]
    with Session(engine) as s:
        assert s.scalar(select(AuditLog.actor).where(AuditLog.action == "content.reject")) == (
            "Олена (адміністратор)"
        )


# --- погодження й журнал -------------------------------------------------------------


def test_approvals_queue(engine, media):
    with Session(engine) as s, s.begin():
        a = approvals.request(s, "publish_post", "Пост «Блонд» на 03.12", {"item_id": 5})
        aid = a.id
    c = build(engine, media)
    login(c)
    assert c.get("/api/me").json()["approvals_pending"] == 1
    rows = c.get("/api/approvals").json()
    assert rows[0]["kind_name"] == "Публікація поста" and rows[0]["payload"] == {"item_id": 5}
    assert c.post(f"/api/approvals/{aid}", json={"approve": True}).json() == {"status": "approved"}
    assert c.post(f"/api/approvals/{aid}", json={"approve": False}).status_code == 409
    assert c.get("/api/approvals").json() == []
    log = c.get("/api/audit").json()
    assert log[0]["action"] == "approval.approved" and log[0]["actor"] == "Маргарита (директор)"


def test_settings_connections(engine, media):
    c = build(engine, media)
    login(c)
    s = c.get("/api/settings").json()
    names = {x["name"]: x["ok"] for x in s["connections"]}
    assert names["Claude"] and names["Gemini"] and not names["Google Ads"]
    assert s["content"]["post_weekday"] == 3 and s["ai_budget"] == 0


def test_studio_unavailable(engine, media):
    c = build(engine, media)
    c.ctx.studio = lambda: None
    login(c)
    assert c.get("/api/content").status_code == 503
    with Session(engine) as s:
        assert s.scalar(select(ContentItem)) is None
