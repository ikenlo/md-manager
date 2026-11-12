"""Пропозиції AI на погодження адміністратора: зберегти, знайти, відхилити, прострочити.

Синхронні функції (SQLAlchemy sync) — викликаються з роутерів FastAPI.
Час — лише aware UTC (`utcnow()`): UTCDateTime відхиляє naive datetime.
"""

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_suggestion import AISuggestion
from app.models.base import utcnow

logger = logging.getLogger(__name__)

# Пропозиція без рішення довше цього — застаріла (клієнт уже чекав надто довго)
PENDING_TTL_HOURS = 24


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


def approve_suggestion(db: Session, suggestion_uuid: str, user_id: int) -> AISuggestion:
    """Виконає proposed_booking, створить повідомлення й поставить у чергу. Буде в 2.3.3b."""
    raise NotImplementedError("approve_suggestion is implemented in Phase 3 Part 2.3.3b")
