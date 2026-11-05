"""Фонові задачі (APScheduler): оновлення токена Instagram (тут і далі — етап 6:
нагадування, автоповернення AI, чистка історії)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import Engine

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

    def start(self) -> AsyncIOScheduler:
        sched = AsyncIOScheduler(timezone="UTC")
        sched.add_job(self.refresh_ig_token, "interval", hours=12, id="ig_token",
                      next_run_time=self.clock())  # fmt: skip
        sched.start()
        return sched
