"""In-process шина подій: воркер і API повідомляють, WebSocket (Фаза 2, частина 3) — слухає.

Один процес (без --workers), тому достатньо списку підписників у пам'яті.
Без підписників `emit` нічого не робить.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger("mds.events")

Payload = dict[str, Any]
Subscriber = Callable[[str, Payload], Awaitable[None]]

# Типи подій
NEW_MESSAGE = "new_message"
MESSAGE_STATUS = "message_status"


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        """Додає підписника; повертає функцію відписки."""
        self._subscribers.append(callback)
        return lambda: self.unsubscribe(callback)

    def unsubscribe(self, callback: Subscriber) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def emit(self, event_type: str, payload: Payload) -> None:
        # Помилка одного підписника не зупиняє інших і не ламає відправника
        for cb in list(self._subscribers):
            try:
                await cb(event_type, payload)
            except Exception:
                log.exception("Підписник події %s впав", event_type)


events = EventBus()
