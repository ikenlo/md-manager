"""Відправка повідомлень: адмін-група і клієнт у його канал.

Канали підключаються через протокол ClientSender (Telegram — етап 3, Instagram — етап 5).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import Channel, Client, Conversation

log = logging.getLogger(__name__)

IG_WINDOW = timedelta(hours=24)


class AdminSender(Protocol):
    async def __call__(self, text: str, keyboard: Any | None = None) -> None: ...


class ClientSender(Protocol):
    """Повертає True, якщо повідомлення доставлено."""

    async def __call__(self, recipient_id: str, text: str) -> bool: ...


def ig_window_open(last_inbound_at: datetime | None, now: datetime | None = None) -> bool:
    if last_inbound_at is None:
        return False
    now = now or datetime.now(UTC)
    return now - last_inbound_at < IG_WINDOW


@dataclass
class Notifier:
    admin_sender: AdminSender | None = None
    senders: dict[Channel, ClientSender] = field(default_factory=dict)

    async def admin(self, text: str, keyboard: Any | None = None) -> None:
        if self.admin_sender is None:
            log.warning("admin notification dropped: no admin sender")
            return
        try:
            await self.admin_sender(text, keyboard)
        except Exception:
            log.exception("admin notification failed")

    def client_channel(
        self, session: Session, client: Client, now: datetime | None = None
    ) -> tuple[Channel, str] | None:
        """Куди зараз можна написати клієнту: Telegram завжди; Instagram — лише у 24-год вікні."""
        if client.tg_user_id and Channel.telegram in self.senders:
            return Channel.telegram, str(client.tg_user_id)
        if client.ig_user_id and Channel.instagram in self.senders:
            conv = session.scalar(
                select(Conversation).where(
                    Conversation.client_id == client.id,
                    Conversation.channel == Channel.instagram,
                )
            )
            if conv and ig_window_open(conv.last_inbound_at, now):
                return Channel.instagram, client.ig_user_id
        return None

    async def send_to_channel(self, channel: Channel, recipient_id: str, text: str) -> bool:
        sender = self.senders.get(channel)
        if sender is None:
            return False
        try:
            return await sender(recipient_id, text)
        except Exception:
            log.exception("send to %s failed", channel.value)
            return False

    async def client(self, engine: Engine, client_id: int, text: str) -> bool:
        with Session(engine) as session:
            client = session.get(Client, client_id)
            target = self.client_channel(session, client) if client else None
        if target is None:
            return False
        return await self.send_to_channel(target[0], target[1], text)
