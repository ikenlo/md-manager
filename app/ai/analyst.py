"""AI-аналітик (Claude): щоденний звіт із порадами й ідеями реклами.

У Claude йдуть лише агрегати (цифри дня, оголошення, пости салону, послуги з цінами) —
жодних імен, телефонів чи переписки клієнтів. Відповідь — строгий JSON за схемою
(structured outputs), результат зберігається в ai_report, вартість — в ai_usage.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai.claude_json import AiUnavailable, ask_json, obj
from app.ai.jobs import Background
from app.analytics import daily
from app.analytics.dashboard import Dashboard
from app.config import Settings
from app.db.models import AiReport, PostStat, Service

log = logging.getLogger(__name__)

WD = ["понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота", "неділя"]

SALON = (
    "Салон краси M&D (Київська область): перукарські послуги, фарбування, манікюр, педикюр, "
    "догляд. Клієнти записуються через Instagram Direct і Telegram-бота. Валюта — гривня."
)

PROMPT_RULES = (
    "Правила:\n"
    "- Пиши українською, коротко й конкретно, на «ви». Без канцеляриту.\n"
    "- Спирайся лише на надані цифри. Не вигадуй цін, акцій, знижок, майстрів чи фактів: "
    "ціни — тільки з каталогу послуг. Якщо даних мало — так і скажи і порадь, що зібрати.\n"
    "- Промпт для зображення — англійською (генератори розуміють її найкраще): "
    "реалістичне фото для соцмереж салону краси, тепле природне світло, "
    "без тексту й логотипів у кадрі, без впізнаваних облич знаменитостей.\n"
    "- Нічого не запускай і не обіцяй від імені салону — ти радиш власнику."
)

DAILY_SYSTEM = (
    f"Ти — маркетолог-аналітик салону. {SALON}\n"
    "Щоранку власник бачить твій звіт на панелі. Проаналізуй вчорашній день порівняно із "
    "середнім за 7 днів, рекламу за 30 днів (що окупається: ціна візиту, а не кліки), "
    "які пости заходять аудиторії, і запропонуй наступні кроки та нові рекламні пости.\n"
    f"{PROMPT_RULES}"
)


S = {"type": "string"}
PLATFORM = {"type": "string", "enum": ["instagram", "facebook", "both"]}

AD_IDEA = obj(
    {
        "platform": PLATFORM,
        "objective": S,
        "service": S,
        "audience": S,
        "headline": S,
        "primary_text": S,
        "cta": S,
        "budget_hint": S,
        "image_prompt": S,
    }
)

DAILY_SCHEMA = obj(
    {
        "summary": S,
        "highlights": {
            "type": "array",
            "items": obj({"tone": {"type": "string", "enum": ["good", "warn", "info"]}, "text": S}),
        },
        "actions": {
            "type": "array",
            "items": obj(
                {
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    "title": S,
                    "why": S,
                    "how": S,
                }
            ),
        },
        "ad_ideas": {"type": "array", "items": AD_IDEA},
    }
)


AnalystUnavailable = AiUnavailable


@dataclass
class Report:
    id: int
    kind: str
    period_start: date
    created_at: datetime
    model: str
    cost_usd: float
    data: dict[str, Any]


def _to_report(r: AiReport) -> Report:
    return Report(
        r.id, r.kind, r.period_start, r.created_at, r.model, r.cost_usd, json.loads(r.payload)
    )


def latest(engine: Engine, kind: str, period_start: date | None = None) -> Report | None:
    with Session(engine) as s:
        q = select(AiReport).where(AiReport.kind == kind)
        if period_start is not None:
            q = q.where(AiReport.period_start == period_start)
        row = s.scalar(q.order_by(AiReport.created_at.desc(), AiReport.id.desc()).limit(1))
        return _to_report(row) if row else None


def next_month(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def _uah(kop: int | float) -> float:
    return round(kop / 100, 2)


def _services_from_catalog(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for x in catalog.get("services") or []:
        price = x.get("price")
        out.append(
            {
                "id": x.get("id"),
                "name": x.get("name"),
                "category": x.get("category") or x.get("section") or "",
                "price_uah": (("від " if x.get("price_from") else "") + f"{price // 100}")
                if isinstance(price, int)
                else None,
                "duration_min": x.get("duration_min"),
            }
        )
    return out


def _services_local(engine: Engine) -> list[dict[str, Any]]:
    with Session(engine) as s:
        return [
            {
                "id": x.id,
                "name": x.name,
                "category": x.category,
                "price_uah": (
                    f"{x.price_from}–{x.price_to}" if x.price_to else f"від {x.price_from}"
                ),
                "duration_min": x.duration_min,
            }
            for x in s.scalars(select(Service).where(Service.is_active.is_(True)))
        ]


def _posts(engine: Engine, since: datetime, tz: Any) -> list[dict[str, Any]]:
    with Session(engine) as s:
        rows = s.scalars(
            select(PostStat)
            .where(PostStat.published_at >= since)
            .order_by(PostStat.published_at.desc())
            .limit(30)
        ).all()
    return [
        {
            "platform": p.platform,
            "published": p.published_at.astimezone(tz).strftime("%Y-%m-%d %H:%M ")
            + WD[p.published_at.astimezone(tz).weekday()],
            "format": p.media_type,
            "caption_start": p.caption[:160],
            "reach": p.reach,
            "views": p.views,
            "likes": p.likes,
            "comments": p.comments,
            "saved": p.saved,
            "shares": p.shares,
        }
        for p in rows
    ]


class Analyst:
    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        claude: Any,
        *,
        mds: Any = None,
        dashboard: Callable[[], Awaitable[Dashboard]] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.claude = claude
        self.mds = mds
        self.dashboard = dashboard
        self.clock = clock

    # --- дані -----------------------------------------------------------------
    async def services(self) -> list[dict[str, Any]]:
        if self.mds is not None:
            try:
                return _services_from_catalog(await self.mds.catalog())
            except Exception:  # noqa: BLE001
                log.warning("analyst: MDS catalog unavailable")
                return []
        return _services_local(self.engine)

    async def snapshot(self) -> dict[str, Any]:
        """Усе, що бачить аналітик. Лише агрегати, без персональних даних клієнтів."""
        now = self.clock()
        tz = self.settings.zone
        day = await daily.build(self.engine, self.settings, now, mds=self.mds)
        services = await self.services()
        snap: dict[str, Any] = {
            "today": f"{now.astimezone(tz):%Y-%m-%d}, {WD[now.astimezone(tz).weekday()]}",
            "yesterday": day.as_dict(),
            "services": services,
            "posts_last_30d": _posts(self.engine, now - timedelta(days=30), tz),
        }
        if self.dashboard is not None:
            db = await self.dashboard()
            names = {s["id"]: s["name"] for s in services}
            snap["last_30d"] = {
                "bookings": db.totals["bookings"],
                "came": db.totals["came"],
                "no_show": db.totals["no_show"],
                "revenue_uah": _uah(db.totals["revenue_kop"]),
                "sources": [
                    {
                        "source": s.source,
                        "bookings": s.bookings,
                        "came": s.came,
                        "revenue_uah": _uah(s.revenue_kop),
                    }
                    for s in db.sources[:12]
                ],  # fmt: skip
                "ads": [
                    {
                        "platform": a.platform,
                        "name": a.name,
                        "campaign": a.campaign,
                        "spend_uah": _uah(a.spend_minor),
                        "impressions": a.impressions,
                        "clicks": a.clicks,
                        "dialogs_or_conversions": a.conversations,
                        "bookings": a.bookings,
                        "came": a.came,
                        "cost_per_visit_uah": _uah(a.cost_per_visit_minor)
                        if a.cost_per_visit_minor is not None
                        else None,
                    }
                    for a in db.ads[:15]
                ],
            }
            if names and self.mds is not None:
                try:
                    visits = await self.mds.visits(db.date_from, db.date_to)
                    top = Counter(
                        names.get(v.get("service_id"), "інше")
                        for v in visits
                        if v.get("status") != "cancelled"
                    )
                    snap["last_30d"]["top_services"] = top.most_common(10)
                except Exception:  # noqa: BLE001
                    pass
        return snap

    # --- Claude ---------------------------------------------------------------
    async def _ask(
        self, system: str, user: str, schema: dict[str, Any], *, expect_out: int, kind: str
    ) -> tuple[dict[str, Any], str, float]:
        return await ask_json(
            self.claude, self.engine, self.settings, self.clock,
            model=self.settings.analyst_model, effort=self.settings.analyst_effort,
            system=system, content=user, schema=schema, expect_out=expect_out, kind=kind,
        )  # fmt: skip

    def _save(self, kind: str, period: date, data: dict[str, Any], model: str, cost: float) -> int:
        with Session(self.engine) as s, s.begin():
            row = AiReport(
                kind=kind,
                period_start=period,
                model=model,
                cost_usd=cost,
                payload=json.dumps(data, ensure_ascii=False),
            )
            s.add(row)
            s.flush()
            return row.id

    async def daily_report(self) -> Report:
        snap = await self.snapshot()
        user = (
            "Дані салону (JSON):\n"
            + json.dumps(snap, ensure_ascii=False, default=str)
            + "\n\nДай: summary (2–3 речення про вчорашній день і тренд), highlights (3–6 "
            "спостережень: що виросло/впало і чому це важливо), actions (3–5 конкретних дій "
            "на сьогодні–тиждень: реклама, пости, робота з неявками, бюджет — з поясненням "
            "«чому» і «як»), ad_ideas (2–3 нові рекламні пости під послуги, що окупаються або "
            "мають вільні години, з текстом оголошення, аудиторією, порадою щодо бюджету "
            "і промптом для картинки)."
        )
        data, model, cost = await self._ask(
            DAILY_SYSTEM, user, DAILY_SCHEMA, expect_out=6000, kind="analysis"
        )
        day = date.fromisoformat(snap["yesterday"]["day"])
        rid = self._save("daily", day, data, model, cost)
        return Report(rid, "daily", day, self.clock(), model, cost, data)


class Hub(Background):
    """Запуск щоденного звіту з сайту у фоні."""

    def __init__(self, analyst: Analyst | None) -> None:
        super().__init__()
        self.analyst = analyst

    @property
    def enabled(self) -> bool:
        return self.analyst is not None and self.analyst.claude is not None

    def start_daily(self) -> bool:
        assert self.analyst is not None
        return self.start("daily", self.analyst.daily_report)
