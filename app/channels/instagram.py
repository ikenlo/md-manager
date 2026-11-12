"""Instagram Direct (Instagram API with Instagram Login, хост graph.instagram.com).

- GET /webhook/instagram — верифікація (hub.mode / hub.verify_token / hub.challenge)
- POST /webhook/instagram — події; підпис X-Hub-Signature-256 = HMAC-SHA256(app secret, тіло)
- власні повідомлення (is_echo) ігноруються, інакше бот говорить сам із собою
- відповідати можна лише у 24-год вікні після останнього повідомлення клієнта
- токен живе 60 днів; оновлюється в scheduler.py і зберігається в salon_settings
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Request, Response
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app import clients as cl
from app.agent.tools import do_handoff
from app.config import Settings
from app.db.models import Channel, Conversation, Message, SalonSetting
from app.notify import Notifier, ig_window_open

log = logging.getLogger(__name__)

GRAPH = "https://graph.instagram.com"
API_VERSION = "v27.0"
MAX_TEXT_BYTES = 1000
TOKEN_KEY = "ig_access_token"
TOKEN_REFRESHED_KEY = "ig_token_refreshed_at"


# --- розбір вебхука ----------------------------------------------------------


@dataclass(frozen=True)
class InboundText:
    sender_id: str
    mid: str
    text: str
    ref: str | None = None  # мітка джерела: оголошення (ig_ad_<id>) або ref із посилання ig.me


@dataclass(frozen=True)
class InboundAttachment:
    sender_id: str
    mid: str
    kinds: tuple[str, ...]


@dataclass(frozen=True)
class Deleted:
    mid: str


Event = InboundText | InboundAttachment | Deleted


def check_signature(body: bytes, header: str | None, app_secret: str) -> bool:
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header.removeprefix("sha256="), expected)


def parse_events(payload: dict[str, Any]) -> list[Event]:
    if payload.get("object") != "instagram":
        return []
    events: list[Event] = []
    for entry in payload.get("entry") or []:
        own_id = str(entry.get("id", ""))
        for item in entry.get("messaging") or []:
            msg = item.get("message")
            if not msg:
                continue  # messaging_seen, postbacks тощо
            mid = str(msg.get("mid", ""))
            if msg.get("is_deleted"):
                events.append(Deleted(mid))
                continue
            sender = str((item.get("sender") or {}).get("id", ""))
            if msg.get("is_echo") or sender == own_id or not sender:
                continue
            if msg.get("text"):
                events.append(InboundText(sender, mid, msg["text"], _referral(item)))
            elif msg.get("attachments"):
                kinds = tuple(str(a.get("type", "file")) for a in msg["attachments"])
                events.append(InboundAttachment(sender, mid, kinds))
    return events


def _referral(item: dict[str, Any]) -> str | None:
    """Звідки прийшли в Direct: реклама (ad_id) або посилання ig.me/m/<акаунт>?ref=…"""
    from app.clients import clean_label

    ref = item.get("referral") or (item.get("message") or {}).get("referral") or {}
    if ref.get("ad_id"):
        return clean_label(f"ig_ad_{ref['ad_id']}")
    return clean_label(ref.get("ref"))


def split_text(text: str, limit: int = MAX_TEXT_BYTES) -> list[str]:
    """Instagram приймає до 1000 байт; ріжемо по абзацах/словах."""
    parts: list[str] = []
    current = ""
    for word in text.replace("\n", "\n ").split(" "):
        candidate = f"{current} {word}" if current else word
        if len(candidate.encode()) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current.replace("\n ", "\n").strip())
        while len(word.encode()) > limit:  # одне дуже довге «слово»
            cut = limit
            while len(word[:cut].encode()) > limit:
                cut -= 1
            parts.append(word[:cut])
            word = word[cut:]
        current = word
    if current.strip():
        parts.append(current.replace("\n ", "\n").strip())
    return parts


# --- API ---------------------------------------------------------------------


class InstagramClient:
    def __init__(
        self, engine: Engine, settings: Settings, http: httpx.AsyncClient | None = None
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.http = http or httpx.AsyncClient(timeout=15)

    def token(self) -> str:
        """Оновлений токен з БД має пріоритет над IG_ACCESS_TOKEN з .env."""
        with Session(self.engine) as s:
            row = s.get(SalonSetting, TOKEN_KEY)
            return row.value if row and row.value else self.settings.ig_access_token

    async def send(self, igsid: str, text: str) -> bool:
        token = self.token()
        if not token:
            log.warning("instagram: no access token")
            return False
        for part in split_text(text):
            r = await self.http.post(
                f"{GRAPH}/{API_VERSION}/me/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"recipient": {"id": igsid}, "message": {"text": part}},
            )
            if r.status_code != 200:
                # У тілі помилки Meta немає персональних даних; текст повідомлення не логуємо.
                log.error("instagram send failed: %s %s", r.status_code, r.text[:300])
                return False
        return True

    async def refresh_token(self, now: datetime | None = None) -> bool:
        """Продовжити 60-денний токен. Meta вимагає, щоб токен був старший за 24 год."""
        now = now or datetime.now(UTC)
        token = self.token()
        if not token:
            return False
        r = await self.http.get(
            f"{GRAPH}/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": token},
        )
        if r.status_code != 200:
            log.error("instagram token refresh failed: %s", r.status_code)
            return False
        new = r.json().get("access_token")
        if not new:
            return False
        with Session(self.engine) as s, s.begin():
            s.merge(SalonSetting(key=TOKEN_KEY, value=new))
            s.merge(SalonSetting(key=TOKEN_REFRESHED_KEY, value=now.isoformat()))
        log.info("instagram token refreshed")
        return True

    def needs_refresh(self, now: datetime, every: timedelta = timedelta(days=7)) -> bool:
        with Session(self.engine) as s:
            row = s.get(SalonSetting, TOKEN_REFRESHED_KEY)
        if row is None:
            return True
        return now - datetime.fromisoformat(row.value) >= every


# --- обробка подій -----------------------------------------------------------


class InstagramHandler:
    def __init__(
        self,
        engine: Engine,
        dialog: Any,
        ig: InstagramClient,
        notifier: Notifier,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.engine = engine
        self.dialog = dialog
        self.ig = ig
        self.notifier = notifier
        self.clock = clock

    def _seen(self, mid: str) -> bool:
        with Session(self.engine) as s:
            return s.scalar(select(Message.id).where(Message.external_id == mid)) is not None

    def _client_id(self, igsid: str) -> int:
        with Session(self.engine) as s, s.begin():
            return cl.get_or_create_ig_client(s, igsid).id

    async def handle(self, event: Event) -> None:
        if isinstance(event, Deleted):
            with Session(self.engine) as s, s.begin():
                s.execute(delete(Message).where(Message.external_id == event.mid))
            return
        if event.mid and self._seen(event.mid):
            return  # Meta повторює доставку до 36 год
        client_id = self._client_id(event.sender_id)

        if isinstance(event, InboundAttachment):
            # Фото/голосові бот не розбирає → людина (часто це «фарбування як на фото»).
            with Session(self.engine) as s, s.begin():
                conv = cl.get_conversation(s, client_id, Channel.instagram)
                kinds = ", ".join(event.kinds)
                cl.add_message(
                    s, conv, cl.MessageRole.client, f"[вкладення: {kinds}]",
                    external_id=event.mid, now=self.clock(),
                )  # fmt: skip
                conv_id, paused = conv.id, conv.state != "ai"
            if not paused:
                await do_handoff(
                    self.engine,
                    self.notifier,
                    conv_id,
                    f"Клієнт надіслав {kinds}",
                    now=self.clock(),
                )
                await self._reply(
                    client_id, "Дякую! Передаю адміністратору — він гляне й відповість тут 🙏"
                )
            return

        reply = await self.dialog.handle_inbound(
            Channel.instagram, client_id, event.text, external_id=event.mid, lead_source=event.ref
        )
        if reply:
            await self._reply(client_id, reply)

    async def _reply(self, client_id: int, text: str) -> None:
        with Session(self.engine) as s:
            conv = s.scalar(
                select(Conversation).where(
                    Conversation.client_id == client_id, Conversation.channel == Channel.instagram
                )
            )
            igsid = conv.client.ig_user_id if conv else None
            window = ig_window_open(conv.last_inbound_at if conv else None, self.clock())
        if not igsid or not window:
            log.warning("instagram: window closed, reply dropped conv")
            return
        if not await self.ig.send(igsid, text):
            await self.notifier.admin(
                f"⚠️ Не вдалося відповісти в Instagram (діалог #{conv.id}). Перевірте токен."
            )


def build_router(
    get_settings: Callable[[], Settings], process: Callable[[list[Event]], Awaitable[None]]
) -> APIRouter:
    router = APIRouter()
    background: set[asyncio.Task[None]] = set()

    @router.get("/webhook/instagram")
    async def verify(request: Request) -> Response:
        settings = get_settings()
        p = request.query_params
        if (
            p.get("hub.mode") == "subscribe"
            and settings.ig_verify_token
            and hmac.compare_digest(p.get("hub.verify_token", ""), settings.ig_verify_token)
        ):
            return Response(p.get("hub.challenge", ""), media_type="text/plain")
        return Response(status_code=403)

    @router.post("/webhook/instagram")
    async def receive(request: Request) -> Response:
        settings = get_settings()
        body = await request.body()
        if not check_signature(
            body, request.headers.get("X-Hub-Signature-256"), settings.ig_app_secret
        ):
            return Response(status_code=403)
        try:
            events = parse_events(await request.json())
        except ValueError:
            return Response(status_code=400)
        if events:
            # Meta чекає швидкого 200; агент може думати до 30 с — обробляємо у фоні.
            task = asyncio.create_task(process(events))
            background.add(task)
            task.add_done_callback(background.discard)
        return Response(status_code=200)

    router.background = background  # type: ignore[attr-defined]  # для тестів
    return router


async def process_events(handler: InstagramHandler, events: list[Event]) -> None:
    for e in events:
        try:
            await handler.handle(e)
        except Exception:
            log.exception("instagram event failed")
