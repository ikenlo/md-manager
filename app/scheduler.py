"""Фонові задачі (APScheduler): нагадування, автоповернення AI після handoff,
оновлення токена Instagram, чистка старої переписки, аналітика Meta/Google,
щоденний AI-звіт і контент-план на наступний місяць."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app import clients as cl
from app import reminders
from app.channels.instagram import InstagramClient
from app.config import Settings
from app.notify import Notifier

log = logging.getLogger(__name__)


class Jobs:
    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        notifier: Notifier,
        ig: InstagramClient | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        meta: Any = None,
        google: Any = None,
        analyst: Any = None,
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.notifier = notifier
        self.ig = ig
        self.clock = clock
        self.meta = meta  # MetaClient: щоденна аналітика Instagram, Facebook і реклами
        self.google = google  # GoogleAdsClient
        self.analyst = analyst  # app.ai.analyst.Analyst

    async def refresh_ig_token(self) -> None:
        if self.ig is None or not self.ig.token():
            return
        now = self.clock()
        if not self.ig.needs_refresh(now):
            return
        if not await self.ig.refresh_token(now):
            await self.notifier.admin(
                "⚠️ Не вдалося оновити токен Instagram. Без нього бот перестане відповідати "
                "в Direct (через 60 днів від останнього оновлення). Перевірте апку в Meta."
            )

    async def reminders(self) -> None:
        if self.settings.mds_url:  # записи й нагадування — у MDS Connect
            return
        await reminders.send_due_reminders(self.engine, self.settings, self.notifier, self.clock())

    async def auto_resume(self) -> None:
        with Session(self.engine) as s, s.begin():
            ids = cl.auto_resume_stale(s, self.settings.handoff_auto_resume_hours, self.clock())
        for cid in ids:
            await self.notifier.admin(
                f"🤖 Діалог #{cid}: {self.settings.handoff_auto_resume_hours} год тиші — "
                "AI знову відповідає"
            )

    async def collect_meta(self) -> None:
        if self.meta is None:
            return
        from app.analytics.meta import MetaError, collect

        try:
            stats = await collect(
                self.engine, self.meta, today=self.clock().astimezone(self.settings.zone).date(),
                tz=self.settings.zone, ig_user_id=self.settings.meta_ig_user_id,
                ad_account_id=self.settings.meta_ad_account_id,
                page_id=self.settings.meta_page_id,
            )  # fmt: skip
            log.info("meta collected: %s", stats)
        except MetaError as e:
            log.error("meta collect failed: %s", e.status)
            await self.notifier.admin(f"⚠️ Не вдалося зібрати аналітику Meta: {e.message}")

    async def collect_google(self) -> None:
        if self.google is None:
            return
        from app.analytics.google_ads import GoogleAdsError, collect

        try:
            stats = await collect(
                self.engine, self.google, today=self.clock().astimezone(self.settings.zone).date()
            )
            log.info("google ads collected: %s", stats)
        except GoogleAdsError as e:
            log.error("google ads collect failed: %s", e.status)
            await self.notifier.admin(f"⚠️ Не вдалося зібрати дані Google Ads: {e.message}")

    def _panel_link(self, path: str) -> str:
        base = self.settings.public_url.rstrip("/")
        return f"\n\nДеталі: {base}{path}" if base else "\n\nДеталі — на панелі /panel."

    async def daily_analysis(self) -> None:
        if self.analyst is None or not self.settings.analyst_daily:
            return
        try:
            report = await self.analyst.daily_report()
        except Exception as e:  # noqa: BLE001
            log.exception("daily analysis failed")
            await self.notifier.admin(f"⚠️ AI-звіт за вчора не готовий: {e}")
            return
        d = report.data
        top = [a.get("title", "") for a in (d.get("actions") or [])[:3]]
        text = f"📊 Звіт за {report.period_start:%d.%m}\n\n{d.get('summary', '')}"
        if top:
            text += "\n\nЩо зробити:\n" + "\n".join(f"• {t}" for t in top)
        await self.notifier.admin(text + self._panel_link("/panel#ai"))

    async def monthly_plan(self) -> None:
        if self.analyst is None:
            return
        from app.ai.analyst import next_month

        month = next_month(self.clock().astimezone(self.settings.zone).date())
        try:
            report = await self.analyst.content_plan(month)
        except Exception as e:  # noqa: BLE001
            log.exception("content plan failed")
            await self.notifier.admin(f"⚠️ Контент-план на {month:%m.%Y} не згенерувався: {e}")
            return
        n = len(report.data.get("posts") or [])
        await self.notifier.admin(
            f"🗓 Контент-план на {month:%m.%Y} готовий: {n} постів з підписами й промптами."
            + self._panel_link(f"/panel/content?m={month:%Y-%m}")
        )

    async def cleanup(self) -> None:
        n = reminders.cleanup_old_messages(self.engine, self.clock())
        if n:
            log.info("cleanup: removed %s old messages", n)

    def start(self) -> AsyncIOScheduler:
        sched = AsyncIOScheduler(timezone="UTC")
        sched.add_job(self.reminders, "interval", minutes=1, id="reminders",
                      max_instances=1, coalesce=True)  # fmt: skip
        sched.add_job(self.auto_resume, "interval", minutes=10, id="auto_resume")
        sched.add_job(self.cleanup, "cron", hour=3, minute=17, id="cleanup")
        sched.add_job(self.collect_meta, "cron", hour=6, minute=30, id="meta",
                      timezone=self.settings.tz)  # fmt: skip
        sched.add_job(self.collect_google, "cron", hour=6, minute=40, id="google_ads",
                      timezone=self.settings.tz)  # fmt: skip
        sched.add_job(self.daily_analysis, "cron", hour=7, minute=5, id="ai_daily",
                      timezone=self.settings.tz)  # fmt: skip
        if self.settings.content_plan_auto_day:
            sched.add_job(self.monthly_plan, "cron", day=self.settings.content_plan_auto_day,
                          hour=10, minute=15, id="ai_plan", timezone=self.settings.tz)  # fmt: skip
        sched.add_job(self.refresh_ig_token, "interval", hours=12, id="ig_token",
                      next_run_time=self.clock())  # fmt: skip
        sched.start()
        return sched
