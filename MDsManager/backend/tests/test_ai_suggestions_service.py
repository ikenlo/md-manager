import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AISuggestion, Dialogue, User
from app.models.base import utcnow
from app.services.ai_suggestions import (
    PENDING_TTL_HOURS,
    approve_suggestion,
    expire_stale,
    get_pending_for_dialogue,
    reject_suggestion,
    save_suggestion,
)


@pytest.fixture
def dialogue(db_session) -> Dialogue:
    return db_session.scalar(select(Dialogue).order_by(Dialogue.id))


@pytest.fixture
def admin(db_session) -> User:
    return db_session.scalar(select(User))


def save(db, dialogue, content="Вітаю! Чим допомогти?", intent="question", booking=None):
    return save_suggestion(db, dialogue.id, None, content, booking, intent)


def test_save_suggestion_creates_pending(db_session, dialogue):
    booking = {
        "tool": "create_appointment",
        "service_name": "Манікюр",
        "date": "2026-12-01",
        "time": "10:00",
    }
    s = save(db_session, dialogue, "Передала на підтвердження", "booking", booking)
    assert s.status == "pending" and str(uuid.UUID(s.uuid)) == s.uuid
    assert s.created_at is not None and s.resolved_at is None
    assert s.proposed_booking == booking and s.intent == "booking"


def test_save_suggestion_expires_old_pending(db_session, dialogue):
    first = save(db_session, dialogue, "Перша")
    second = save(db_session, dialogue, "Друга")
    db_session.expire_all()
    assert first.status == "expired" and first.resolved_at is not None
    assert second.status == "pending"


def test_save_suggestion_keeps_other_dialogues(db_session, dialogue):
    other = db_session.scalar(select(Dialogue).where(Dialogue.id != dialogue.id))
    a = save(db_session, dialogue)
    b = save(db_session, other)
    db_session.expire_all()
    assert a.status == "pending" and b.status == "pending"


def test_get_pending_returns_latest(db_session, dialogue):
    save(db_session, dialogue, "Перша")
    second = save(db_session, dialogue, "Друга")
    assert get_pending_for_dialogue(db_session, dialogue.id).uuid == second.uuid


def test_get_pending_none_when_empty(db_session, dialogue, admin):
    assert get_pending_for_dialogue(db_session, dialogue.id) is None
    s = save(db_session, dialogue)
    reject_suggestion(db_session, s.uuid, admin.id)
    assert get_pending_for_dialogue(db_session, dialogue.id) is None


def test_reject_suggestion_sets_status(db_session, dialogue, admin):
    s = save(db_session, dialogue)
    got = reject_suggestion(db_session, s.uuid, admin.id)
    assert got.status == "rejected" and got.resolved_by_user_id == admin.id
    assert got.resolved_at is not None


def test_reject_non_pending_raises(db_session, dialogue, admin):
    s = save(db_session, dialogue)
    s.status, s.resolved_at = "approved", utcnow()
    db_session.commit()
    with pytest.raises(ValueError, match="'approved', not 'pending'"):
        reject_suggestion(db_session, s.uuid, admin.id)


def test_reject_unknown_raises(db_session, admin):
    with pytest.raises(ValueError, match="not found"):
        reject_suggestion(db_session, "unknown-uuid", admin.id)


def test_expire_stale_expires_old(db_session, dialogue):
    other = db_session.scalar(select(Dialogue).where(Dialogue.id != dialogue.id))
    old = save(db_session, dialogue)
    old.created_at = utcnow() - timedelta(hours=PENDING_TTL_HOURS + 1)
    fresh = save(db_session, other)
    db_session.commit()

    assert expire_stale(db_session) == 1
    db_session.expire_all()
    assert old.status == "expired" and old.resolved_at is not None
    assert fresh.status == "pending"
    assert expire_stale(db_session) == 0


def test_approve_not_implemented(db_session, dialogue, admin):
    s = save(db_session, dialogue)
    with pytest.raises(NotImplementedError):
        approve_suggestion(db_session, s.uuid, admin.id)
    assert (
        db_session.scalar(select(AISuggestion.status).where(AISuggestion.uuid == s.uuid))
        == "pending"
    )
