import asyncio
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.models import AISuggestion, Dialogue, Message, OutboundQueue, User
from app.models.base import utcnow
from app.services.ai_suggestions import (
    PENDING_TTL_HOURS,
    approve_suggestion,
    expire_stale,
    get_pending_for_dialogue,
    reject_suggestion,
    save_suggestion,
)
from app.services.events import events


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


BOOKING = {
    "tool": "create_appointment",
    "service_name": "Манікюр",
    "date": "2026-12-01",
    "time": "10:00",
    "arguments": {"service_name": "Манікюр", "date": "2026-12-01", "time": "10:00"},
}
PENDING_TEXT = "Передала ваш запит на підтвердження адміністратору."


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def approve(db, uuid_, user_id):
    return asyncio.run(approve_suggestion(db, uuid_, user_id))


def test_approve_creates_message_and_queue(db_session, dialogue, admin):
    dialogue.status = "new"
    db_session.commit()
    s = save(db_session, dialogue, PENDING_TEXT, "booking", BOOKING)
    msgs_before = count(db_session, Message)

    got = approve(db_session, s.uuid, admin.id)

    assert got.status == "approved" and got.resolved_by_user_id == admin.id
    assert got.resolved_at is not None
    # інструмент виконано (mock create_appointment) — результат збережено для звірки
    assert got.proposed_booking["result"]["ok"] is True
    assert got.proposed_booking["result"]["booking_id"].startswith("mock_")
    assert count(db_session, Message) == msgs_before + 1
    msg = db_session.scalar(select(Message).order_by(Message.id.desc()))
    assert (msg.direction, msg.status, msg.sender_type) == ("outbound", "queued", "agent")
    assert msg.content == PENDING_TEXT and msg.dialogue_id == dialogue.id
    q = db_session.scalar(select(OutboundQueue).where(OutboundQueue.message_id == msg.id))
    assert q.status == "pending" and q.attempts == 0
    db_session.expire_all()
    assert dialogue.last_message_at == msg.created_at and dialogue.status == "in_progress"


def test_approve_without_booking(db_session, dialogue, admin, monkeypatch):
    import app.services.ai_suggestions as mod

    async def must_not_run(*_a, **_k):
        raise AssertionError("no tool call expected")

    monkeypatch.setattr(mod, "execute_tool", must_not_run)
    s = save(db_session, dialogue, "Манікюр коштує 350 грн 😊", "question")
    got = approve(db_session, s.uuid, admin.id)
    assert got.status == "approved" and got.proposed_booking is None
    msg = db_session.scalar(select(Message).order_by(Message.id.desc()))
    assert msg.content == "Манікюр коштує 350 грн 😊"
    assert db_session.scalar(select(OutboundQueue).where(OutboundQueue.message_id == msg.id))


def test_approve_non_pending_raises(db_session, dialogue, admin):
    s = save(db_session, dialogue)
    s.status, s.resolved_at = "approved", utcnow()
    db_session.commit()
    with pytest.raises(ValueError, match="'approved', not 'pending'"):
        approve(db_session, s.uuid, admin.id)


def test_approve_unknown_uuid_raises(db_session, admin):
    with pytest.raises(ValueError, match="not found"):
        approve(db_session, "unknown", admin.id)


def test_approve_tool_error_raises(db_session, dialogue, admin):
    bad = {**BOOKING, "service_name": "Неіснуюча послуга"}
    s = save(db_session, dialogue, PENDING_TEXT, "booking", bad)
    msgs, queue = count(db_session, Message), count(db_session, OutboundQueue)

    with pytest.raises(ValueError, match="Booking failed: Невідома послуга"):
        approve(db_session, s.uuid, admin.id)

    db_session.expire_all()
    assert count(db_session, Message) == msgs and count(db_session, OutboundQueue) == queue
    got = db_session.scalar(select(AISuggestion).where(AISuggestion.uuid == s.uuid))
    assert got.status == "pending" and got.resolved_at is None
    assert "result" not in got.proposed_booking


def test_approve_emits_event(db_session, dialogue, admin):
    seen = []

    async def on(event_type, payload):
        seen.append((event_type, payload))

    unsubscribe = events.subscribe(on)
    try:
        s = save(db_session, dialogue, "Так, є час о 13:00", "question")
        approve(db_session, s.uuid, admin.id)
    finally:
        unsubscribe()
    msg = db_session.scalar(select(Message).order_by(Message.id.desc()))
    assert len(seen) == 1
    event_type, payload = seen[0]
    assert event_type == "new_message" and payload["dialogue_uuid"] == dialogue.uuid
    m = payload["message"]
    assert m["uuid"] == msg.uuid and m["content"] == "Так, є час о 13:00"
    assert (m["direction"], m["status"], m["sender_type"]) == ("outbound", "queued", "agent")


def test_double_approve_sends_once(db_session, dialogue, admin):
    s = save(db_session, dialogue, PENDING_TEXT, "booking", BOOKING)
    msgs = count(db_session, Message)

    async def both():
        return await asyncio.gather(
            approve_suggestion(db_session, s.uuid, admin.id),
            approve_suggestion(db_session, s.uuid, admin.id),
            return_exceptions=True,
        )

    results = asyncio.run(both())
    assert sum(isinstance(r, AISuggestion) for r in results) == 1
    assert sum(isinstance(r, ValueError) for r in results) == 1
    assert count(db_session, Message) == msgs + 1


def test_hourly_cleanup_job_registered_and_runs(db_session, dialogue, session_factory, monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main
    from app.config import get_settings

    old = save(db_session, dialogue)
    old.created_at = utcnow() - timedelta(hours=PENDING_TTL_HOURS + 1)
    db_session.commit()

    monkeypatch.setattr(main, "SessionLocal", session_factory)
    main._hourly_cleanup()
    db_session.expire_all()
    assert old.status == "expired"

    monkeypatch.setattr(get_settings(), "outbound_worker_enabled", True)
    app = main.create_app()
    with TestClient(app, base_url="http://localhost"):
        job = app.state.scheduler.get_job("expire_ai_suggestions")
        assert job is not None and job.trigger.interval == timedelta(hours=1)
