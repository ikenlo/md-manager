import asyncio
import contextlib
import inspect
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.database import get_db
from app.services.auth import user_by_token
from app.services.ws_manager import manager

router = APIRouter()
log = logging.getLogger("mds.ws")

# Сервер шле ping і заодно перевіряє, чи токен ще чинний (вихід, оновлення токена)
PING_SECONDS = 30


def _user_id_for(ws: WebSocket, token: str) -> int | None:
    """Коротка сесія БД через get_db (з урахуванням dependency_overrides у тестах)."""
    if not token:
        return None
    provider = ws.app.dependency_overrides.get(get_db, get_db)
    got = provider()
    db = next(got) if inspect.isgenerator(got) else got
    try:
        user = user_by_token(db, token)
        return user.id if user else None
    finally:
        if inspect.isgenerator(got):
            got.close()


@router.websocket("/api/ws")
async def ws_endpoint(ws: WebSocket, token: str = "") -> None:
    user_id = _user_id_for(ws, token)
    if user_id is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return

    await manager.connect(ws, user_id)

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(PING_SECONDS)
            if _user_id_for(ws, token) is None:
                await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Session ended")
                return
            await ws.send_json({"type": "ping"})

    hb = asyncio.create_task(heartbeat())
    try:
        while True:
            data = await ws.receive_json()
            if isinstance(data, dict) and data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            # інші типи (typing, mark_read) — Фаза 3
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        hb.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await hb
        await manager.disconnect(ws, user_id)
