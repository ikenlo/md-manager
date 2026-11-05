"""Клієнти й діалоги: пошук/створення, повідомлення, стан (ai / paused)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    Booking,
    Channel,
    Client,
    Conversation,
    ConversationState,
    Message,
    MessageRole,
    SalonSetting,
)

AI_PAUSED_KEY = "ai_paused"
_LABEL_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def clean_label(raw: str | None) -> str | None:
    """Мітка джерела з посилання t.me/<бот>?start=<мітка> або реклами; сміття → None."""
    raw = (raw or "").strip()
    return raw if _LABEL_RE.fullmatch(raw) else None


def get_or_create_tg_client(session: Session, tg_user_id: int, name: str = "") -> Client:
    client = session.scalar(select(Client).where(Client.tg_user_id == tg_user_id))
    if client is None:
        client = Client(tg_user_id=tg_user_id, name=name[:100])
        session.add(client)
        session.flush()
    elif name and not client.name:
        client.name = name[:100]
    return client


def get_or_create_ig_client(session: Session, ig_user_id: str, name: str = "") -> Client:
    client = session.scalar(select(Client).where(Client.ig_user_id == ig_user_id))
    if client is None:
        client = Client(ig_user_id=ig_user_id, name=name[:100])
        session.add(client)
        session.flush()
    return client


def find_client_by_phone(session: Session, phone: str) -> Client | None:
    return session.scalar(select(Client).where(Client.phone == phone))


def attach_phone(session: Session, client: Client, phone: str) -> Client:
    """Прив'язати телефон. Якщо такий телефон уже є в іншого клієнта —
    об'єднати (той самий клієнт написав з іншого каналу)."""
    other = find_client_by_phone(session, phone)
    if other is None or other.id == client.id:
        client.phone = phone
        return client
    # Переносимо канали й записи на клієнта з телефоном.
    for attr in ("tg_user_id", "ig_user_id"):
        value = getattr(client, attr)
        if value and not getattr(other, attr):
            setattr(client, attr, None)
            session.flush()
            setattr(other, attr, value)
    if client.name and not other.name:
        other.name = client.name
    for b in session.scalars(select(Booking).where(Booking.client_id == client.id)):
        b.client_id = other.id
    for conv in session.scalars(select(Conversation).where(Conversation.client_id == client.id)):
        existing = session.scalar(
            select(Conversation).where(
                Conversation.client_id == other.id, Conversation.channel == conv.channel
            )
        )
        if existing is None:
            conv.client_id = other.id
        else:
            for msg in conv.messages:
                msg.conversation_id = existing.id
            session.flush()
            session.delete(conv)
    session.flush()
    session.delete(client)
    session.flush()
    return other


def get_conversation(session: Session, client_id: int, channel: Channel) -> Conversation:
    conv = session.scalar(
        select(Conversation).where(
            Conversation.client_id == client_id, Conversation.channel == channel
        )
    )
    if conv is None:
        conv = Conversation(client_id=client_id, channel=channel, state=ConversationState.ai)
        session.add(conv)
        session.flush()
    return conv


def add_message(
    session: Session,
    conv: Conversation,
    role: MessageRole,
    text: str,
    *,
    external_id: str | None = None,
    now: datetime | None = None,
) -> Message:
    now = now or datetime.now(UTC)
    msg = Message(
        conversation_id=conv.id, role=role, text=text, external_id=external_id, created_at=now
    )
    session.add(msg)
    if role == MessageRole.client:
        conv.last_inbound_at = now
    session.flush()
    return msg


def recent_messages(session: Session, conv: Conversation, limit: int = 20) -> list[Message]:
    rows = session.scalars(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.id.desc())
        .limit(limit)
    )
    return list(reversed(list(rows)))


def pause(session: Session, conv: Conversation, now: datetime | None = None) -> None:
    conv.state = ConversationState.paused
    conv.paused_at = now or datetime.now(UTC)


def resume(session: Session, conv: Conversation) -> None:
    conv.state = ConversationState.ai
    conv.paused_at = None


def auto_resume_stale(session: Session, hours: int, now: datetime | None = None) -> list[int]:
    """Повернути AI в діалоги, де після паузи `hours` год ніхто не писав."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=hours)
    resumed = []
    for conv in session.scalars(
        select(Conversation).where(
            Conversation.state == ConversationState.paused, Conversation.paused_at < cutoff
        )
    ):
        last = session.scalar(
            select(Message.created_at)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.id.desc())
            .limit(1)
        )
        if last is None or last < cutoff:
            resume(session, conv)
            resumed.append(conv.id)
    return resumed


def ai_globally_paused(session: Session) -> bool:
    row = session.get(SalonSetting, AI_PAUSED_KEY)
    return bool(row and row.value == "1")


def set_ai_globally_paused(session: Session, paused: bool) -> None:
    session.merge(SalonSetting(key=AI_PAUSED_KEY, value="1" if paused else "0"))


def forget_client(session: Session, client: Client) -> None:
    """Повне видалення клієнта на його прохання (/forget)."""
    conv_ids = list(
        session.scalars(select(Conversation.id).where(Conversation.client_id == client.id))
    )
    if conv_ids:
        session.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
        session.execute(delete(Conversation).where(Conversation.id.in_(conv_ids)))
    session.execute(delete(Booking).where(Booking.client_id == client.id))
    session.delete(client)
    session.flush()


def get_conversation_by_id(session: Session, conversation_id: int) -> Conversation:
    conv = session.get(Conversation, conversation_id)
    if conv is None:
        raise LookupError(f"conversation {conversation_id} not found")
    return conv
