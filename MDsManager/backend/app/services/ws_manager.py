"""Активні WebSocket-з'єднання. Один процес — стан у пам'яті."""

import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("mds.ws")


class ConnectionManager:
    def __init__(self) -> None:
        self.active: dict[int, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, user_id: int) -> None:
        await ws.accept()
        self.active.setdefault(user_id, []).append(ws)

    async def disconnect(self, ws: WebSocket, user_id: int) -> None:
        sockets = self.active.get(user_id)
        if sockets and ws in sockets:
            sockets.remove(ws)
        if sockets is not None and not sockets:
            self.active.pop(user_id, None)

    async def send_to_user(self, user_id: int, payload: dict[str, Any]) -> None:
        for ws in list(self.active.get(user_id, [])):
            try:
                await ws.send_json(payload)
            except Exception:  # вкладку закрили без close-frame — прибираємо
                log.info("WS: прибираю розірване з'єднання користувача %s", user_id)
                await self.disconnect(ws, user_id)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Усім користувачам (один салон — усі бачать спільний інбокс)."""
        for user_id in list(self.active):
            await self.send_to_user(user_id, payload)

    def count(self) -> int:
        return sum(len(v) for v in self.active.values())


manager = ConnectionManager()


async def forward_to_ws(event_type: str, payload: dict[str, Any]) -> None:
    """Підписник шини подій: кожна подія → усім відкритим вкладкам."""
    await manager.broadcast({"type": event_type, **payload})
