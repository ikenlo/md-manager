"""Фонові задачі (APScheduler): нагадування, автоповернення AI після handoff,
оновлення токена Instagram, чистка старої переписки."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

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
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.notifier = notifier
        self.ig = ig
        self.clock = clock

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
        sched.add_job(self.refresh_ig_token, "interval", hours=12, id="ig_token",
                      next_run_time=self.clock())  # fmt: skip
        sched.start()
        return sched
