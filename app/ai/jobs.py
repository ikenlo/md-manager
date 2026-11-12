"""Фонові задачі, запущені з сайту (генерація триває секунди–хвилини)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.ai.budget import BudgetExceeded
from app.ai.claude_json import AiUnavailable

log = logging.getLogger(__name__)


class Background:
    def __init__(self) -> None:
        self.running: set[str] = set()
        self.errors: dict[str, str] = {}
        self._tasks: set[asyncio.Task[Any]] = set()

    def start(self, key: str, coro_factory: Callable[[], Awaitable[Any]]) -> bool:
        """False — така задача вже виконується (повторне натискання нічого не запускає)."""
        if key in self.running:
            return False
        self.running.add(key)
        self.errors.pop(key, None)

        async def run() -> None:
            try:
                await coro_factory()
            except (AiUnavailable, BudgetExceeded, ValueError) as e:
                self.errors[key] = str(e)
            except Exception:  # noqa: BLE001
                log.exception("background job %s failed", key)
                self.errors[key] = "Не вдалося виконати — деталі в логах сервера."
            finally:
                self.running.discard(key)

        task = asyncio.create_task(run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    async def wait(self) -> None:
        """Для тестів: дочекатися всіх запущених задач."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
