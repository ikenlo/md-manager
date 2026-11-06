"""AI-аналітик (Claude): щоденний звіт із порадами й ідеями реклами, контент-план на місяць.

У Claude йдуть лише агрегати (цифри дня, оголошення, пости салону, послуги з цінами) —
жодних імен, телефонів чи переписки клієнтів. Відповідь — строгий JSON за схемою
(structured outputs), результат зберігається в ai_report, вартість — в ai_usage.
"""

from __future__ import annotations

import asyncio
import calendar
import json
import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.agent import usage
from app.ai import budget, prices
from app.analytics import daily
from app.analytics.dashboard import Dashboard
from app.config import Settings
from app.db.models import AiReport, PostStat, Service

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
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
    "- Промпти для зображень і відео — англійською (генератори розуміють її найкраще): "
    "реалістичне фото/відео для соцмереж салону краси, тепле природне світло, "
    "без тексту й логотипів у кадрі, без впізнаваних облич знаменитостей. "
    "Відео — вертикальне 9:16, 8–10 секунд, опиши 2–4 плани, рух камери і звук.\n"
    "- Нічого не запускай і не обіцяй від імені салону — ти радиш власнику."
)

DAILY_SYSTEM = (
    f"Ти — маркетолог-аналітик салону. {SALON}\n"
    "Щоранку власник бачить твій звіт на панелі. Проаналізуй вчорашній день порівняно із "
    "середнім за 7 днів, рекламу за 30 днів (що окупається: ціна візиту, а не кліки), "
    "які пости заходять аудиторії, і запропонуй наступні кроки та нові рекламні пости.\n"
    f"{PROMPT_RULES}"
)

PLAN_SYSTEM = (
    f"Ти — SMM-стратег салону. {SALON}\n"
    "Склади контент-план на місяць для Instagram і Facebook: чергуй рубрики (результати "
    "робіт до/після, процес, поради догляду, майстри й атмосфера, відгуки, сезонні послуги, "
    "закулісся), формати (Reels, карусель, пост, сторіс) і дні з найкращим охопленням. "
    "Ураховуй свята й сезон в Україні цього місяця. До кожного поста — готовий підпис, "
    "хештеги, заклик до дії (запис у Direct або Telegram), промпт для зображення і для відео.\n"
    f"{PROMPT_RULES}"
)


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


S = {"type": "string"}
PLATFORM = {"type": "string", "enum": ["instagram", "facebook", "both"]}

AD_IDEA = _obj(
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
        "video_prompt": S,
    }
)

DAILY_SCHEMA = _obj(
    {
        "summary": S,
        "highlights": {
            "type": "array",
            "items": _obj(
                {"tone": {"type": "string", "enum": ["good", "warn", "info"]}, "text": S}
            ),
        },
        "actions": {
            "type": "array",
            "items": _obj(
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

POST = _obj(
    {
        "date": {"type": "string", "description": "YYYY-MM-DD"},
        "time": {"type": "string", "description": "HH:MM за Києвом"},
        "platform": PLATFORM,
        "format": {"type": "string", "enum": ["reels", "carousel", "post", "stories"]},
        "rubric": S,
        "title": S,
        "caption": S,
        "hashtags": {"type": "array", "items": S},
        "cta": S,
        "image_prompt": S,
        "video_prompt": S,
    }
)

PLAN_SCHEMA = _obj(
    {
        "theme": S,
        "goals": {"type": "array", "items": S},
        "posts": {"type": "array", "items": POST},
    }
)


class AnalystUnavailable(Exception):
    pass


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
        if self.claude is None:
            raise AnalystUnavailable("AI-аналітик потребує ANTHROPIC_API_KEY")
        model = self.settings.analyst_model
        with Session(self.engine) as s:
            budget.check(
                s,
                self.settings.ai_monthly_budget_usd,
                self.clock(),
                self.settings.zone,
                prices.text_cost(model, (len(system) + len(user)) // 2, expect_out),
            )
        async with self.claude.beta.messages.stream(
            model=model,
            max_tokens=64000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": self.settings.analyst_effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            msg = await stream.get_final_message()
        served = getattr(msg, "model", None) or model
        with Session(self.engine) as s, s.begin():
            cost = usage.record(s, None, served, msg.usage, kind=kind).cost_usd
        if msg.stop_reason == "refusal":
            raise AnalystUnavailable("Модель відмовилась відповідати — спробуйте пізніше")
        if msg.stop_reason == "max_tokens":
            raise AnalystUnavailable("Відповідь обірвалась (ліміт токенів) — спробуйте ще раз")
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            return json.loads(text), served, cost
        except ValueError as e:
            raise AnalystUnavailable("AI повернув некоректну відповідь") from e

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
            "мають вільні години, з текстом оголошення, аудиторією, порадою щодо бюджету, "
            "промптами для картинки й відео)."
        )
        data, model, cost = await self._ask(
            DAILY_SYSTEM, user, DAILY_SCHEMA, expect_out=6000, kind="analysis"
        )
        day = date.fromisoformat(snap["yesterday"]["day"])
        rid = self._save("daily", day, data, model, cost)
        return Report(rid, "daily", day, self.clock(), model, cost, data)

    async def content_plan(self, month: date) -> Report:
        month = month.replace(day=1)
        snap = await self.snapshot()
        days_in = calendar.monthrange(month.year, month.month)[1]
        n = self.settings.content_plan_posts
        user = (
            f"Місяць плану: {month:%Y-%m} ({days_in} днів, 1-ше число — "
            f"{WD[month.weekday()]}). Постів: {n} (розподіли рівномірно; Reels — щонайменше "
            "третина; частину постів — для обох мереж, частину — окремо для Facebook, де "
            "аудиторія старша).\n"
            "Що вже відомо про салон і аудиторію (JSON):\n"
            + json.dumps(
                {
                    "services": snap["services"],
                    "posts_last_30d": snap["posts_last_30d"],
                    "last_30d": snap.get("last_30d"),
                },
                ensure_ascii=False,
                default=str,
            )
            + "\n\nДати — лише в межах цього місяця, у форматі YYYY-MM-DD, за зростанням."
        )
        data, model, cost = await self._ask(
            PLAN_SYSTEM, user, PLAN_SCHEMA, expect_out=1200 * n, kind="plan"
        )
        prefix = f"{month:%Y-%m}-"
        data["posts"] = sorted(
            (p for p in data.get("posts") or [] if str(p.get("date", "")).startswith(prefix)),
            key=lambda p: (p["date"], p.get("time", "")),
        )
        rid = self._save("content_plan", month, data, model, cost)
        return Report(rid, "content_plan", month, self.clock(), model, cost, data)


class Hub:
    """Запуск звіту/плану у фоні з панелі (генерація триває до кількох хвилин)."""

    def __init__(self, analyst: Analyst | None) -> None:
        self.analyst = analyst
        self.running: set[str] = set()
        self.errors: dict[str, str] = {}
        self._tasks: set[asyncio.Task[Any]] = set()

    @property
    def enabled(self) -> bool:
        return self.analyst is not None and self.analyst.claude is not None

    def start(self, key: str, coro_factory: Callable[[], Awaitable[Any]]) -> bool:
        if key in self.running:
            return False
        self.running.add(key)
        self.errors.pop(key, None)

        async def run() -> None:
            try:
                await coro_factory()
            except (AnalystUnavailable, budget.BudgetExceeded) as e:
                self.errors[key] = str(e)
            except Exception:  # noqa: BLE001
                log.exception("analyst job %s failed", key)
                self.errors[key] = "Не вдалося згенерувати — деталі в логах сервера."
            finally:
                self.running.discard(key)

        task = asyncio.create_task(run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    def start_daily(self) -> bool:
        assert self.analyst is not None
        return self.start("daily", self.analyst.daily_report)

    def start_plan(self, month: date) -> bool:
        assert self.analyst is not None
        return self.start(f"plan:{month:%Y-%m}", lambda: self.analyst.content_plan(month))
