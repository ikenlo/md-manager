"""Пропозиції AI на погодження адміністратора: зберегти, знайти, погодити, відхилити, прострочити.

save/get/reject/expire — синхронні (SQLAlchemy sync);
approve — async: виконує інструмент і надсилає подію.
Час — лише aware UTC (`utcnow()`): UTCDateTime відхиляє naive datetime.
"""

import asyncio
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AISuggestion, Message, OutboundQueue
from app.models.base import utcnow
from app.services.events import NEW_MESSAGE, events
from app.services.tools import execute_tool

logger = logging.getLogger(__name__)

# Пропозиція без рішення довше цього — застаріла (клієнт уже чекав надто довго)
PENDING_TTL_HOURS = 24

# Один процес (без --workers): погодження йдуть по черзі — подвійний клік двох адміністраторів
# не створить два записи й не надішле клієнту два однакові повідомлення
_approve_lock = asyncio.Lock()


def save_suggestion(
    db: Session,
    dialogue_id: int,
    message_id: int | None,
    content: str,
    proposed_booking: dict[str, Any] | None,
    intent: str,
) -> AISuggestion:
    """Зберігає нову пропозицію (результат run_agent).

    Попередні pending того ж діалогу стають expired: актуальна лише відповідь
    на останнє повідомлення клієнта.
    """
    now = utcnow()
    existing = db.scalars(
        select(AISuggestion).where(
            AISuggestion.dialogue_id == dialogue_id,
            AISuggestion.status == "pending",
        )
    ).all()
    for s in existing:
        s.status = "expired"
        s.resolved_at = now

    suggestion = AISuggestion(
        dialogue_id=dialogue_id,
        message_id=message_id,
        content=content,
        proposed_booking=proposed_booking,
        intent=intent,
        status="pending",
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    logger.info(
        "AI suggestion saved: uuid=%s, dialogue=%s, intent=%s, expired_prev=%d",
        suggestion.uuid,
        dialogue_id,
        intent,
        len(existing),
    )
    return suggestion


def get_pending_for_dialogue(db: Session, dialogue_id: int) -> AISuggestion | None:
    """Поточна pending-пропозиція діалогу, якщо є."""
    return db.scalar(
        select(AISuggestion)
        .where(AISuggestion.dialogue_id == dialogue_id, AISuggestion.status == "pending")
        .order_by(AISuggestion.created_at.desc(), AISuggestion.id.desc())
        .limit(1)
    )


def _get_pending_or_raise(db: Session, suggestion_uuid: str) -> AISuggestion:
    suggestion = db.scalar(select(AISuggestion).where(AISuggestion.uuid == suggestion_uuid))
    if suggestion is None:
        raise ValueError(f"Suggestion {suggestion_uuid} not found")
    if suggestion.status != "pending":
        raise ValueError(f"Suggestion status is '{suggestion.status}', not 'pending'")
    return suggestion


def reject_suggestion(db: Session, suggestion_uuid: str, user_id: int) -> AISuggestion:
    """Відхиляє pending-пропозицію. ValueError — не знайдено або вже не pending."""
    suggestion = _get_pending_or_raise(db, suggestion_uuid)
    suggestion.status = "rejected"
    suggestion.resolved_at = utcnow()
    suggestion.resolved_by_user_id = user_id
    db.commit()
    db.refresh(suggestion)
    logger.info("AI suggestion rejected: uuid=%s, by_user=%s", suggestion_uuid, user_id)
    return suggestion


def expire_stale(db: Session) -> int:
    """Прострочує pending, старіші за PENDING_TTL_HOURS. Повертає кількість.

    Для щогодинної задачі планувальника (app/main.py lifespan).
    """
    now = utcnow()
    cutoff = now - timedelta(hours=PENDING_TTL_HOURS)
    stale = db.scalars(
        select(AISuggestion).where(
            AISuggestion.status == "pending",
            AISuggestion.created_at < cutoff,
        )
    ).all()
    for s in stale:
        s.status = "expired"
        s.resolved_at = now
    if stale:
        db.commit()
        logger.info(
            "Expired %d stale AI suggestions (older than %dh)", len(stale), PENDING_TTL_HOURS
        )
    return len(stale)


async def approve_suggestion(db: Session, suggestion_uuid: str, user_id: int) -> AISuggestion:
    """Погоджує пропозицію AI.

    1. Якщо є proposed_booking — виконує інструмент (create_appointment). Помилка → ValueError,
       у БД нічого не змінюється, пропозиція лишається pending.
    2. Текст AI стає вихідним повідомленням (sender_type=agent) і йде в чергу відправки.
    3. Статус approved; подія new_message — після commit.
    ValueError — не знайдено, вже не pending або запис не вдався.
    """
    async with _approve_lock:
        suggestion = _get_pending_or_raise(db, suggestion_uuid)
        dialogue = suggestion.dialogue
        booking = suggestion.proposed_booking

        # Інструмент — до будь-яких змін у БД: його збій нічого не лишає по собі
        if booking:
            args = {k: booking.get(k) for k in ("service_name", "date", "time")}
            tool = booking.get("tool") or "create_appointment"
            tool_result = await execute_tool(tool, args)
            if tool_result.get("error"):
                db.rollback()
                logger.warning(
                    "AI suggestion approve failed: uuid=%s, tool=%s", suggestion_uuid, tool
                )
                raise ValueError(f"Booking failed: {tool_result['error']}")
            # новий dict — щоб SQLAlchemy помітив зміну JSON; booking_id лишається для звірки
            suggestion.proposed_booking = {**booking, "result": tool_result}

        try:
            now = utcnow()
            msg = Message(
                dialogue_id=dialogue.id,
                sender_type="agent",
                content=suggestion.content,
                direction="outbound",
                status="queued",
                created_at=now,
            )
            db.add(msg)
            db.flush()
            db.add(OutboundQueue(message_id=msg.id, status="pending", next_retry_at=now))
            dialogue.last_message_at = now
            if dialogue.status == "new":
                dialogue.status = "in_progress"
            suggestion.status = "approved"
            suggestion.resolved_at = now
            suggestion.resolved_by_user_id = user_id
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(suggestion)
        db.refresh(msg)

    # Подія — після commit і поза блокуванням (той самий формат, що в POST /messages)
    from app.api.routes.dialogues import message_out  # пізній імпорт: сервіс ← роутер

    await events.emit(
        NEW_MESSAGE,
        {"dialogue_uuid": dialogue.uuid, "message": message_out(msg).model_dump(mode="json")},
    )
    logger.info(
        "AI suggestion approved: uuid=%s, dialogue=%s, user=%s, message_uuid=%s, booking=%s",
        suggestion_uuid,
        dialogue.id,
        user_id,
        msg.uuid,
        bool(booking),
    )
    return suggestion
