"""Статистика дня, AI-аналітик (щоденний звіт, контент-план) і їх сторінки на панелі."""

import asyncio
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import analyst as an
from app.ai.budget import BudgetExceeded
from app.ai.claude_json import FALLBACK_BETA
from app.analytics import daily, dashboard
from app.config import Settings
from app.db.models import AdDaily, AiReport, AiUsage, MetricDaily, PostStat
from app.notify import Notifier
from app.scheduler import Jobs

NOW = datetime(2026, 11, 20, 6, 0, tzinfo=UTC)  # 08:00 Київ → «вчора» = 19.11
YDAY = date(2026, 11, 19)
PHONE = "+380671234567"

REPORT = {
    "summary": "Вчора 3 нові записи — вище середнього.",
    "highlights": [{"tone": "good", "text": "Reels з блондом <b>набрав</b> 900 охоплення"}],
    "actions": [
        {
            "priority": "high",
            "title": "Підняти бюджет блонду",
            "why": "ціна візиту 150 грн",
            "how": "+20% на 3 дні",
        },  # fmt: skip
    ],
    "ad_ideas": [
        {
            "platform": "instagram",
            "objective": "діалоги",
            "service": "Фарбування",
            "audience": "жінки 25–45, 10 км",
            "headline": "Блонд без жовтизни",
            "primary_text": "Запишіться в Direct",
            "cta": "Написати",
            "budget_hint": "150 грн/день",
            "image_prompt": "Close-up of cool blonde hair <img>",
            "video_prompt": "9:16, 8s",
        },
    ],  # fmt: skip
}


def message(data, stop_reason="end_turn", model="claude-opus-5-5"):
    return SimpleNamespace(
        model=model,
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""),
                 SimpleNamespace(type="text", text=json.dumps(data, ensure_ascii=False))],
        usage=SimpleNamespace(input_tokens=10_000, output_tokens=3_000,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )  # fmt: skip


class FakeAnthropic:
    """Імітує client.beta.messages.stream(...) як async context manager."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[dict] = []
        self.beta = SimpleNamespace(messages=self)

    def stream(self, **kw):
        self.requests.append(kw)
        resp = self.responses.pop(0)
        outer = self

        class _S:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get_final_message(self):
                assert outer
                return resp

        return _S()


class FakeMds:
    async def visits(self, d_from, d_to):
        return [
            # вчора: 2 створено, 1 прийшов (1000 грн), 1 неявка; скасований не рахується у візити
            {"created_at": "2026-11-19T10:00", "starts_at": "2026-11-19T15:00",
             "status": "completed", "paid_amount": 100000, "service_id": 1,
             "client_phone": PHONE, "client_name": "Олена"},
            {"created_at": "2026-11-19T11:00", "starts_at": "2026-11-19T17:00",
             "status": "no_show", "paid_amount": None, "service_id": 1},
            {"created_at": "2026-11-12T11:00", "starts_at": "2026-11-19T12:00",
             "status": "cancelled", "service_id": 2},
            # тиждень до: 7 записів по одному на день, 2 прийшли
            *[{"created_at": f"2026-11-{d:02d}T09:00", "starts_at": f"2026-11-{d:02d}T13:00",
               "status": "completed" if d % 3 == 0 else "scheduled", "paid_amount": 70000,
               "service_id": 2} for d in range(12, 19)],
        ]  # fmt: skip

    async def catalog(self):
        return {
            "services": [
                {"id": 1, "name": "Фарбування", "category": "Волосся", "price": 250000,
                 "price_from": True, "duration_min": 180},
                {"id": 2, "name": "Манікюр", "category": "Нігті", "price": 60000,
                 "price_from": False, "duration_min": 90},
            ],
            "masters": [{"id": 1, "name": "Маргарита Іваненко"}],
        }  # fmt: skip


def settings(**kw):
    return Settings(_env_file=None, anthropic_api_key="k", **kw)


def seed_social(engine):
    with Session(engine) as s, s.begin():
        for d in range(12, 20):
            day = date(2026, 11, d)
            s.add(MetricDaily(day=day, source="instagram", metric="reach",
                              value=2000 if d == 19 else 1000))  # fmt: skip
            s.add(MetricDaily(day=day, source="facebook", metric="page_media_view", value=50))
            s.add(AdDaily(day=day, platform="meta", ad_id="555", ad_name="Блонд",
                          spend_minor=10000, clicks=10, conversations=2))  # fmt: skip
        s.add(AdDaily(day=YDAY, platform="google", ad_id="42", ad_name="Пошук",
                      spend_minor=5000, impressions=100, clicks=4))  # fmt: skip
        s.add(PostStat(platform="instagram", post_id="m1", published_at=NOW, media_type="REELS",
                       caption="Блонд", permalink="https://instagram.com/p/m1",
                       reach=900))  # fmt: skip


# --- статистика дня ----------------------------------------------------------


async def test_day_stats_vs_week(engine):
    seed_social(engine)
    day = await daily.build(engine, settings(), NOW, mds=FakeMds())
    assert day.day == YDAY
    r = {(x.group, x.key): x for x in day.rows}
    # 12.11 створено 2 (один потім скасували) + по одному 13–18 → 8 за 7 днів
    assert (r["salon", "created"].value, r["salon", "created"].avg) == (2, pytest.approx(8 / 7))
    assert r["salon", "planned"].value == 2  # скасований не в графіку
    assert (r["salon", "came"].value, r["salon", "no_show"].value) == (1, 1)
    assert r["salon", "revenue"].value == 100000 and r["salon", "revenue"].money
    assert r["instagram", "reach"].delta == pytest.approx(1.0)
    assert r["facebook", "page_media_view"].avg == 50
    assert r["meta_ads", "spend"].value == 10000 and r["meta_ads", "conv"].avg == 2
    g = r["google_ads", "spend"]
    assert (g.value, g.avg) == (5000, 0)  # раніше Google не крутився — середнє 0, не «немає даних»
    assert [g for g, _ in day.groups()] == ["salon", "instagram", "facebook", "meta_ads",
                                            "google_ads"]  # fmt: skip


async def test_day_stats_mds_down(engine):
    class Down:
        async def visits(self, *a):
            raise RuntimeError("down")

    day = await daily.build(engine, settings(), NOW, mds=Down())
    assert day.rows == [] and "MDS Connect" in day.notes[0]


# --- аналітик -----------------------------------------------------------------


def make_analyst(engine, claude, **kw):
    st = settings(**kw)
    mds = FakeMds()

    async def dash():
        return await dashboard.build(engine, st, NOW, mds=mds)

    return an.Analyst(engine, st, claude, mds=mds, dashboard=dash, clock=lambda: NOW)


async def test_daily_report_saved_without_personal_data(engine):
    seed_social(engine)
    claude = FakeAnthropic(message(REPORT))
    rep = await make_analyst(engine, claude).daily_report()
    assert rep.period_start == YDAY and rep.data["summary"].startswith("Вчора")
    (req,) = claude.requests
    assert req["model"] == "claude-opus-5-5"
    assert req["fallbacks"] == "default" and req["betas"] == [FALLBACK_BETA]
    assert req["output_config"]["format"]["type"] == "json_schema"
    prompt = req["messages"][0]["content"]
    assert PHONE not in prompt and "Олена" not in prompt and "Маргарита" not in prompt
    assert "Фарбування" in prompt and "Блонд" in prompt and '"від 2500"' in prompt
    assert "top_services" in prompt
    with Session(engine) as s:
        row = s.scalar(select(AiReport))
        use = s.scalar(select(AiUsage))
    assert row.kind == "daily" and json.loads(row.payload) == REPORT
    assert use.kind == "analysis" and use.cost_usd == pytest.approx((10_000 * 4 + 3_000 * 20) / 1e6)
    assert an.latest(engine, "daily").id == row.id


async def test_schema_is_strict():
    def check(node):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
            for v in node["properties"].values():
                check(v)
        if node.get("type") == "array":
            check(node["items"])

    check(an.DAILY_SCHEMA)


async def test_refusal_and_truncation_not_saved(engine):
    a = make_analyst(engine, FakeAnthropic(message({}, "refusal"), message({}, "max_tokens")))
    for _ in range(2):
        with pytest.raises(an.AnalystUnavailable):
            await a.daily_report()
    with Session(engine) as s:
        assert s.scalar(select(AiReport)) is None
        assert len(s.scalars(select(AiUsage)).all()) == 2  # витрати все одно враховані


async def test_budget_blocks_call(engine):
    with Session(engine) as s, s.begin():
        s.add(AiUsage(provider="anthropic", kind="chat", model="m", cost_usd=9.99, created_at=NOW))
    claude = FakeAnthropic(message(REPORT))
    with pytest.raises(BudgetExceeded):
        await make_analyst(engine, claude, ai_monthly_budget_usd=10).daily_report()
    assert claude.requests == []


async def test_no_claude():
    with pytest.raises(an.AnalystUnavailable, match="ANTHROPIC_API_KEY"):
        await an.Analyst(None, settings(), None)._ask("s", "u", {}, expect_out=1, kind="x")


def test_next_month():
    assert an.next_month(date(2026, 12, 25)) == date(2027, 1, 1)
    assert an.next_month(date(2026, 1, 31)) == date(2026, 2, 1)


# --- фонові задачі ------------------------------------------------------------


async def test_hub_runs_once_and_keeps_error(engine):
    gate = asyncio.Event()

    async def slow():
        await gate.wait()
        raise an.AnalystUnavailable("Модель відмовилась")

    hub = an.Hub(make_analyst(engine, FakeAnthropic()))
    assert hub.enabled
    assert hub.start("daily", slow) and not hub.start("daily", slow)
    assert "daily" in hub.running
    gate.set()
    for _ in range(5):
        await asyncio.sleep(0)
    assert "daily" not in hub.running and hub.errors["daily"] == "Модель відмовилась"


async def test_scheduler_daily_notify(engine):
    sent = []

    async def admin(text, keyboard=None):
        sent.append(text)

    claude = FakeAnthropic(message(REPORT))
    a = make_analyst(engine, claude)
    jobs = Jobs(engine, settings(public_url="https://bot.md.ua"), Notifier(admin_sender=admin),
                clock=lambda: datetime(2026, 11, 25, 8, 0, tzinfo=UTC), analyst=a)  # fmt: skip
    await jobs.daily_analysis()
    assert "📊 Звіт за 19.11" in sent[0] and "• Підняти бюджет блонду" in sent[0]
    assert "https://bot.md.ua/#/overview" in sent[0]


async def test_scheduler_reports_failure(engine):
    sent = []

    async def admin(text, keyboard=None):
        sent.append(text)

    a = make_analyst(engine, FakeAnthropic(message({}, "refusal")))
    await Jobs(engine, settings(), Notifier(admin_sender=admin), analyst=a).daily_analysis()
    assert sent and sent[0].startswith("⚠️ AI-звіт")
