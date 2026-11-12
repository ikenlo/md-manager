"""Аналітика Meta, дашборд і панель власника."""

import json
from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics import dashboard, google_ads
from app.analytics.google_ads import GoogleAdsClient, GoogleAdsError
from app.analytics.meta import MetaClient, MetaError, collect
from app.booking.slots import KYIV
from app.config import Settings
from app.db.models import AdDaily, AiUsage, MetricDaily, PostStat

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
        if p.endswith("/ig1/media"):
            return httpx.Response(200, json={"data": [
                {"id": "m1", "caption": "Блонд <script>", "media_type": "VIDEO",
                 "media_product_type": "REELS", "timestamp": "2026-11-18T15:00:00+0000",
                 "permalink": "https://www.instagram.com/reel/m1/", "like_count": 40,
                 "comments_count": 3},
                {"id": "m2", "caption": "Стара сторіс", "media_type": "IMAGE",
                 "timestamp": "2026-11-10T09:00:00+0000", "permalink": "javascript:alert(1)",
                 "like_count": 5},
            ]})  # fmt: skip
        if p.endswith("/m1/insights"):
            return httpx.Response(200, json={"data": [
                {"name": "reach", "values": [{"value": 900}]},
                {"name": "views", "total_value": {"value": 2500}},
                {"name": "saved", "values": [{"value": 12}]},
            ]})  # fmt: skip
        if p.endswith("/m2/insights"):
            return httpx.Response(400, json={"error": {"message": "no insights"}})
        if p.endswith("/page1") and q.get("fields") == "access_token":
            return httpx.Response(200, json={"access_token": "page-tok", "id": "page1"})
        if p.endswith("/page1/insights"):
            assert req.headers["Authorization"] == "Bearer page-tok"
            metrics = q["metric"].split(",")
            if len(metrics) > 1 or metrics == ["page_daily_follows_unique"]:
                return httpx.Response(400, json={"error": {"message": "invalid metric"}})
            return httpx.Response(
                200,
                json={"data": [{"name": metrics[0], "period": "day", "values": [{"value": 77}]}]},
            )
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
    assert stats == {"ig_days": 3, "ad_rows": 2, "posts": 2}
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


async def test_dashboard_without_meta_or_mds(engine):
    db = await dashboard.build(engine, Settings(_env_file=None), NOW)
    assert db.ads == [] and db.followers is None
    assert any("Meta не підключено" in n for n in db.notes)


async def test_collect_facebook_skips_unknown_metric_and_saves_posts(engine, client):
    stats = await collect(engine, client, today=TODAY, tz=KYIV, ig_user_id="ig1", page_id="page1")
    assert stats["fb_days"] == 3
    with Session(engine) as s:
        fb = {
            m.metric for m in s.scalars(select(MetricDaily).where(MetricDaily.source == "facebook"))
        }
        assert fb == {"page_media_view", "page_total_media_view_unique", "page_post_engagements"}
        posts = {p.post_id: p for p in s.scalars(select(PostStat))}
    assert (posts["m1"].media_type, posts["m1"].reach, posts["m1"].views) == ("REELS", 900, 2500)
    assert posts["m1"].saved == 12 and posts["m2"].reach == 0  # без insights — не падаємо


class FakeGoogle:
    def __init__(self):
        self.requests: list[httpx.Request] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        if req.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "ya29", "expires_in": 3600})
        body = json.loads(req.content)
        if body.get("pageToken") == "n2":
            return httpx.Response(200, json={"results": [
                {"segments": {"date": "2026-11-19"}, "campaign": {"id": "42", "name": "Пошук"},
                 "metrics": {"impressions": "300", "clicks": "30", "costMicros": "125500000",
                             "conversions": 2.6}}]})  # fmt: skip
        return httpx.Response(200, json={"results": [
            {"segments": {"date": "2026-11-18"}, "campaign": {"id": "42", "name": "Пошук"},
             "metrics": {"impressions": "200", "clicks": "10", "costMicros": "50000000"}}],
            "nextPageToken": "n2"})  # fmt: skip


async def test_google_ads_collect(engine):
    fake = FakeGoogle()
    g = GoogleAdsClient(
        developer_token="dev", client_id="cid", client_secret="sec", refresh_token="rt",
        customer_id="123-456-7890", login_customer_id="999",
        http=httpx.AsyncClient(transport=httpx.MockTransport(fake)),
    )  # fmt: skip
    assert await google_ads.collect(engine, g, today=TODAY) == {"google_rows": 2}
    search = [r for r in fake.requests if r.url.host == "googleads.googleapis.com"]
    assert search[0].url.path == "/v22/customers/1234567890/googleAds:search"
    assert search[0].headers["developer-token"] == "dev"
    assert search[0].headers["login-customer-id"] == "999"
    assert "BETWEEN '2026-11-17' AND '2026-11-19'" in json.loads(search[0].content)["query"]
    assert sum(r.url.host == "oauth2.googleapis.com" for r in fake.requests) == 1  # токен кешується
    with Session(engine) as s:
        rows = s.scalars(select(AdDaily).order_by(AdDaily.day)).all()
    assert [(r.platform, r.ad_id, r.spend_minor, r.clicks, r.conversations) for r in rows] == [
        ("google", "42", 5000, 10, 0),
        ("google", "42", 12550, 30, 3),
    ]


async def test_google_ads_bad_refresh_token(engine):
    def handler(req):
        return httpx.Response(400, json={"error": "invalid_grant"})

    g = GoogleAdsClient(
        developer_token="d", client_id="c", client_secret="s", refresh_token="r", customer_id="1",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )  # fmt: skip
    with pytest.raises(GoogleAdsError, match="REFRESH_TOKEN"):
        await google_ads.collect(engine, g, today=TODAY)


class GoogleVisits:
    async def visits(self, d_from, d_to):  # noqa: ANN001
        return [{"status": "completed", "paid_amount": 90000,
                 "attribution": {"lead_source": "gads_42"}}]  # fmt: skip


async def test_dashboard_google_campaign_attribution(engine):
    with Session(engine) as s, s.begin():
        s.add(AdDaily(day=date(2026, 11, 19), platform="google", ad_id="42", ad_name="Пошук",
                      spend_minor=30000, clicks=5))  # fmt: skip
        s.add(AdDaily(day=date(2026, 11, 19), platform="meta", ad_id="42", ad_name="Сторіс",
                      spend_minor=1000))  # fmt: skip
    db = await dashboard.build(engine, Settings(_env_file=None), NOW, mds=GoogleVisits())
    by = {a.platform: a for a in db.ads}
    assert by["google"].came == 1 and by["google"].cost_per_visit_minor == 30000
    assert by["meta"].came == 0  # той самий id, інша платформа — не плутаємо
