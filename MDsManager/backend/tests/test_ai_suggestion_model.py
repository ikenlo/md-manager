import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select

from app.models import AISuggestion, Dialogue, Message, User
from app.models.base import utcnow


@pytest.fixture
def dialogue(db_session) -> Dialogue:
    return db_session.scalar(select(Dialogue).order_by(Dialogue.id))


def add(db, **kw) -> AISuggestion:
    s = AISuggestion(**{"content": "Вітаю! Чим допомогти?", "intent": "question", **kw})
    db.add(s)
    db.commit()
    db.expire_all()  # читаємо з БД, а не з пам'яті
    return db.get(AISuggestion, s.id)


def test_create_suggestion_defaults(db_session, dialogue):
    s = add(db_session, dialogue_id=dialogue.id)
    assert s.status == "pending"
    assert str(uuid.UUID(s.uuid)) == s.uuid
    assert s.created_at is not None and s.created_at.tzinfo is UTC
    assert s.resolved_at is None and s.resolved_by_user_id is None
    assert s.dialogue.uuid == dialogue.uuid and s in dialogue.ai_suggestions


def test_suggestion_proposed_booking_json(db_session, dialogue):
    booking = {"service_name": "Манікюр", "date": "2026-12-01", "time": "10:00"}
    s = add(db_session, dialogue_id=dialogue.id, intent="booking", proposed_booking=booking)
    assert s.proposed_booking == booking


def test_suggestion_null_proposed_booking(db_session, dialogue):
    assert add(db_session, dialogue_id=dialogue.id).proposed_booking is None


def test_cascade_delete_dialogue(db_session, dialogue):
    msg = db_session.scalar(select(Message).where(Message.dialogue_id == dialogue.id))
    add(db_session, dialogue_id=dialogue.id, message_id=msg.id)
    # видалення на рівні БД — перевіряємо саме ON DELETE CASCADE
    db_session.execute(delete(Dialogue).where(Dialogue.id == dialogue.id))
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(AISuggestion)) == 0


def test_suggestion_status_transitions(db_session, dialogue):
    admin = db_session.scalar(select(User))
    s = add(db_session, dialogue_id=dialogue.id)
    when = utcnow()
    s.status, s.resolved_at, s.resolved_by_user_id = "approved", when, admin.id
    db_session.commit()
    db_session.expire_all()
    got = db_session.get(AISuggestion, s.id)
    assert got.status == "approved" and got.resolved_by_user_id == admin.id
    assert got.resolved_at == when


def test_naive_resolved_at_rejected(db_session, dialogue):
    s = add(db_session, dialogue_id=dialogue.id)
    s.resolved_at = datetime(2026, 12, 1, 10, 0)  # без часової зони
    with pytest.raises(Exception, match="naive"):
        db_session.commit()
    db_session.rollback()
