"""Аналітика Meta, дашборд і панель власника."""

import json
from datetime import UTC, date, datetime

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import panel
from app.analytics import dashboard
from app.analytics.meta import MetaClient, MetaError, collect
from app.booking.slots import KYIV
from app.config import Settings
from app.db.models import AdDaily, AiUsage, MetricDaily

NOW = datetime(2026, 11, 20, 8, 0, tzinfo=UTC)
TODAY = date(2026, 11, 20)
CONV = "onsite_conversion.messaging_conversation_started_7d"
NEXT_PAGE = "https://graph.facebook.com/v26.0/act_77/insights?after=p2"


class FakeMeta:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.fail = False

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        if self.fail:
            return httpx.Response(400, json={"error": {"message": "Invalid OAuth access token"}})
        p, q = req.url.path, req.url.params
        if p.endswith("/insights") and "act_" not in p:
            day = datetime.fromtimestamp(int(q["since"]), KYIV).day
            return httpx.Response(200, json={"data": [
                {"name": "reach", "period": "day", "total_value": {"value": 100 * day}},
                {"name": "views", "period": "day", "total_value": {"value": 300 * day}},
                {"name": "profile_links_taps", "period": "day", "total_value": {"value": day}},
            ]})  # fmt: skip
        if p.endswith("/ig1"):
            return httpx.Response(200, json={"followers_count": 1234, "id": "ig1"})
        if p.endswith("/act_77/insights"):
            if q.get("after") == "p2":
                return httpx.Response(200, json={"data": [
                    {"date_start": "2026-11-19", "ad_id": "555", "ad_name": "Блонд <b>",
                     "campaign_name": "Фарбування",
                     "impressions": "800", "reach": "600", "clicks": "20", "spend": "150.50",
                     "actions": [{"action_type": CONV, "value": "3"}]}]})  # fmt: skip
            return httpx.Response(200, json={
                "data": [{"date_start": "2026-11-18", "ad_id": "555", "ad_name": "Блонд <b>",
                          "campaign_name": "Фарбування", "impressions": "1000", "reach": "700",
                          "clicks": "25", "spend": "149.50",
                          "actions": [{"action_type": "link_click", "value": "25"},
                                      {"action_type": CONV, "value": "4"}]}],
                "paging": {"next": NEXT_PAGE}})  # fmt: skip
        return httpx.Response(404, json={"error": {"message": "unknown"}})


@pytest.fixture
def fake():
    return FakeMeta()


@pytest.fixture
def client(fake):
    return MetaClient("tok", "v26.0", httpx.AsyncClient(transport=httpx.MockTransport(fake)))


async def test_collect_instagram_and_ads(engine, client, fake):
    stats = await collect(
        engine, client, today=TODAY, tz=KYIV, ig_user_id="ig1", ad_account_id="77"
    )
    assert stats == {"ig_days": 3, "ad_rows": 2}
    ig_req = fake.requests[0]
    assert ig_req.url.path == "/v26.0/ig1/insights"
    assert ig_req.headers["Authorization"] == "Bearer tok"
    assert ig_req.url.params["metric_type"] == "total_value"
    since = int(ig_req.url.params["since"])
    assert datetime.fromtimestamp(since, KYIV) == datetime(2026, 11, 17, tzinfo=KYIV)
    ads_req = next(r for r in fake.requests if "act_77" in r.url.path)
    assert json.loads(ads_req.url.params["time_range"]) == {
        "since": "2026-11-17",
        "until": "2026-11-19",
    }
    with Session(engine) as s:
        reach = dict(
            s.execute(
                select(MetricDaily.day, MetricDaily.value).where(MetricDaily.metric == "reach")
            ).all()
        )
        assert reach == {
            date(2026, 11, 17): 1700,
            date(2026, 11, 18): 1800,
            date(2026, 11, 19): 1900,
        }
        assert (
            s.scalar(select(MetricDaily.value).where(MetricDaily.metric == "followers_count"))
            == 1234
        )
        ads = s.scalars(select(AdDaily).order_by(AdDaily.day)).all()
        assert [(a.day, a.spend_minor, a.conversations) for a in ads] == [
            (date(2026, 11, 18), 14950, 4),
            (date(2026, 11, 19), 15050, 3),
        ]


async def test_collect_twice_updates_not_duplicates(engine, client):
    for _ in range(2):
        await collect(engine, client, today=TODAY, tz=KYIV, ig_user_id="ig1", ad_account_id="77")
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(MetricDaily)) == 3 * 3 + 1
        assert s.scalar(select(func.count()).select_from(AdDaily)) == 2


async def test_meta_error(engine, client, fake):
    fake.fail = True
    with pytest.raises(MetaError, match="OAuth"):
        await collect(engine, client, today=TODAY, tz=KYIV, ig_user_id="ig1")


class FakeMdsVisits:
    async def visits(self, d_from, d_to):  # noqa: ANN001
        return [
            {
                "status": "completed",
                "paid_amount": 250000,
                "attribution": {"lead_source": "ig_ad_555"},
            },
            {
                "status": "completed",
                "paid_amount": 150000,
                "attribution": {"lead_source": "ig_ad_555"},
            },
            {"status": "no_show", "paid_amount": None, "attribution": {"lead_source": "ig_ad_555"}},
            {"status": "completed", "paid_amount": 50000, "client_source": "рекомендація"},
        ]


async def test_dashboard_links_ads_to_visits(engine, client):
    await collect(engine, client, today=TODAY, tz=KYIV, ig_user_id="ig1", ad_account_id="77")
    with Session(engine) as s, s.begin():
        s.add(AiUsage(provider="gemini", kind="text", model="m", cost_usd=0.5, created_at=NOW))
    settings = Settings(_env_file=None, meta_token="t", ai_monthly_budget_usd=30)
    db = await dashboard.build(engine, settings, NOW, mds=FakeMdsVisits())
    (ad,) = db.ads
    assert (ad.spend_minor, ad.conversations, ad.bookings, ad.came) == (30000, 7, 3, 2)
    assert ad.cost_per_visit_minor == 15000
    assert db.totals == {"bookings": 4, "came": 3, "no_show": 1, "revenue_kop": 450000}
    assert db.followers == 1234 and len(db.ig_series["reach"]) == 3
    assert db.ai_month_total == pytest.approx(0.5)
    html = panel.render(db)
    assert "Блонд &lt;b&gt;" in html and "Блонд <b>" not in html
    assert "150 грн" in html and "4 500 грн" in html and "$0.50 з $30" in html


async def test_dashboard_without_meta_or_mds(engine):
    db = await dashboard.build(engine, Settings(_env_file=None), NOW)
    assert db.ads == [] and db.followers is None
    assert any("Meta не підключено" in n for n in db.notes)
    assert "Даних Instagram ще немає" in panel.render(db)


def _app(settings, db):
    async def get_db():
        return db

    app = FastAPI()
    app.include_router(panel.build_router(lambda: settings, get_db))
    return TestClient(app, base_url="https://testserver")


async def test_panel_login(engine):
    db = await dashboard.build(engine, Settings(_env_file=None), NOW)
    off = _app(Settings(_env_file=None), db)
    assert off.get("/panel").status_code == 404
    c = _app(Settings(_env_file=None, panel_password="s3cret-pass"), db)
    r = c.get("/panel")
    assert r.status_code == 200 and "Пароль" in r.text and "Звідки записи" not in r.text
    assert c.post("/panel/login", data={"password": "nope"}).status_code == 401
    r = c.post("/panel/login", data={"password": "s3cret-pass"}, follow_redirects=False)
    assert r.status_code == 303 and "httponly" in r.headers["set-cookie"].lower()
    r = c.get("/panel")
    assert "Звідки записи" in r.text and "Реклама: що окупається" in r.text
    c.cookies.clear()
    c.cookies.set(panel.COOKIE, "forged")
    assert "Звідки записи" not in c.get("/panel").text
