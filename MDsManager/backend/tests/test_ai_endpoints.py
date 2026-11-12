import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models import AISuggestion, Channel, CrmClient, Dialogue, Message, OutboundQueue
from app.models.base import utcnow
from app.services.ai_suggestions import save_suggestion

BOOKING = {
    "tool": "create_appointment",
    "service_name": "Манікюр",
    "date": "2026-12-01",
    "time": "10:00",
    "arguments": {"service_name": "Манікюр", "date": "2026-12-01", "time": "10:00"},
}


@pytest.fixture(autouse=True)
def _fast_mock_llm(monkeypatch):
    # MockOllamaAdapter за замовчуванням чекає 0,5 с — у тестах не потрібно
    import app.services.adapters.ollama_mock as mock

    monkeypatch.setattr(mock.MockOllamaAdapter.__init__, "__defaults__", (0,))


@pytest.fixture
def dialogue(db_session) -> Dialogue:
    return db_session.scalar(select(Dialogue).order_by(Dialogue.id))


def url(d, tail):
    uuid_ = d if isinstance(d, str) else d.uuid
    return f"/api/dialogues/{uuid_}/ai/{tail}"


def seed(db, d, content="Хвилинку, уточнюю деталі.", intent="booking", booking=BOOKING):
    return save_suggestion(db, d.id, None, content, booking, intent)


def last_outbound(db, d) -> Message:
    return db.scalar(
        select(Message)
        .where(Message.dialogue_id == d.id, Message.direction == "outbound")
        .order_by(Message.id.desc())
    )


def test_respond_creates_suggestion(client, auth, db_session, dialogue):
    r = client.post(url(dialogue, "respond"), headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["content"] == "Тестова відповідь від AI. 😊"
    assert body["intent"] == "question" and body["needs_approval"] is False
    assert body["proposed_booking"] is None
    s = db_session.scalar(select(AISuggestion).where(AISuggestion.uuid == body["suggestion_uuid"]))
    assert s.status == "pending" and s.dialogue_id == dialogue.id
    last = db_session.scalar(
        select(Message).where(Message.dialogue_id == dialogue.id).order_by(Message.id.desc())
    )
    assert s.message_id == last.id
    # клієнту нічого не надіслано
    assert db_session.scalar(select(func.count()).select_from(OutboundQueue)) == 0


def test_respond_empty_dialogue_400(client, auth, db_session):
    d = Dialogue(
        client=CrmClient(name="Без повідомлень"),
        channel=db_session.scalar(select(Channel)),
        status="new",
    )
    db_session.add(d)
    db_session.commit()
    r = client.post(url(d, "respond"), headers=auth)
    assert r.status_code == 400 and r.json()["detail"] == "Dialogue has no messages"


def test_respond_unknown_dialogue_404(client, auth):
    assert client.post(url("nope", "respond"), headers=auth).status_code == 404


def test_respond_ai_disabled_503(client, auth, dialogue, monkeypatch):
    monkeypatch.setattr(get_settings(), "ollama_enabled", False)
    assert client.post(url(dialogue, "respond"), headers=auth).status_code == 503


def test_pending_returns_current(client, auth, dialogue):
    assert client.get(url(dialogue, "pending"), headers=auth).json() == {"suggestion": None}
    made = client.post(url(dialogue, "respond"), headers=auth).json()
    got = client.get(url(dialogue, "pending"), headers=auth).json()["suggestion"]
    assert got["uuid"] == made["suggestion_uuid"] and got["status"] == "pending"
    assert got["content"] == made["content"] and got["created_at"]


def test_approve_default_text_for_booking(client, auth, db_session, dialogue):
    s = seed(db_session, dialogue)
    r = client.post(url(dialogue, f"{s.uuid}/approve"), headers=auth, json={})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved" and body["suggestion_uuid"] == s.uuid
    msg = last_outbound(db_session, dialogue)
    assert body["message_uuid"] == msg.uuid
    assert msg.content == "Вас записано на Манікюр 01.12.2026 о 10:00. Чекаємо вас! 😊"
    assert (msg.status, msg.sender_type) == ("queued", "agent")
    db_session.expire_all()
    got = db_session.get(AISuggestion, s.id)
    assert got.status == "approved" and got.content == msg.content
    assert got.proposed_booking["result"]["ok"] is True


def test_approve_custom_text(client, auth, db_session, dialogue):
    s = seed(db_session, dialogue)
    r = client.post(
        url(dialogue, f"{s.uuid}/approve"), headers=auth, json={"message_text": "  Свій текст  "}
    )
    assert r.status_code == 200
    assert last_outbound(db_session, dialogue).content == "Свій текст"


def test_approve_question_uses_ai_content(client, auth, db_session, dialogue):
    s = seed(db_session, dialogue, content="350 грн", intent="question", booking=None)
    r = client.post(url(dialogue, f"{s.uuid}/approve"), headers=auth, json={"message_text": " "})
    assert r.status_code == 200
    assert last_outbound(db_session, dialogue).content == "350 грн"


def test_approve_empty_content_400(client, auth, db_session, dialogue):
    s = seed(db_session, dialogue, content="", intent="unknown", booking=None)
    r = client.post(url(dialogue, f"{s.uuid}/approve"), headers=auth, json={})
    assert r.status_code == 400
    db_session.expire_all()
    assert db_session.get(AISuggestion, s.id).status == "pending"


def test_approve_booking_failure_400_nothing_sent(client, auth, db_session, dialogue):
    s = seed(db_session, dialogue, booking={**BOOKING, "service_name": "Неіснуюча"})
    before = last_outbound(db_session, dialogue)
    r = client.post(url(dialogue, f"{s.uuid}/approve"), headers=auth, json={})
    assert r.status_code == 400 and "Booking failed" in r.json()["detail"]
    db_session.expire_all()
    got = db_session.get(AISuggestion, s.id)
    assert got.status == "pending" and got.content == "Хвилинку, уточнюю деталі."
    assert last_outbound(db_session, dialogue) == before


def test_approve_non_pending_400(client, auth, db_session, dialogue):
    s = seed(db_session, dialogue)
    s.status, s.resolved_at = "approved", utcnow()
    db_session.commit()
    r = client.post(url(dialogue, f"{s.uuid}/approve"), headers=auth, json={})
    assert r.status_code == 400 and "'approved'" in r.json()["detail"]


def test_approve_unknown_404(client, auth, db_session, dialogue):
    assert client.post(url(dialogue, "nope/approve"), headers=auth, json={}).status_code == 404
    # пропозиція іншого діалогу — теж 404
    other = db_session.scalar(select(Dialogue).where(Dialogue.id != dialogue.id))
    s = seed(db_session, other)
    assert client.post(url(dialogue, f"{s.uuid}/approve"), headers=auth, json={}).status_code == 404


def test_reject_sets_status(client, auth, db_session, dialogue):
    s = seed(db_session, dialogue)
    r = client.post(
        url(dialogue, f"{s.uuid}/reject"), headers=auth, json={"reason": "Невірний час"}
    )
    assert r.status_code == 200 and r.json() == {"suggestion_uuid": s.uuid, "status": "rejected"}
    db_session.expire_all()
    assert db_session.get(AISuggestion, s.id).status == "rejected"
    again = client.post(url(dialogue, f"{s.uuid}/reject"), headers=auth, json={})
    assert again.status_code == 400


def test_ai_endpoints_require_auth(client, db_session, dialogue):
    s = seed(db_session, dialogue)
    assert client.post(url(dialogue, f"{s.uuid}/approve"), json={}).status_code == 401
    assert client.post(url(dialogue, f"{s.uuid}/reject"), json={}).status_code == 401
    assert client.post(url(dialogue, "respond")).status_code == 401
    assert client.get(url(dialogue, "pending")).status_code == 401


CONFIRMATION = "Вас записано на Манікюр 01.12.2026 о 10:00. Чекаємо вас! 😊"


def test_respond_includes_suggested_message_for_booking(client, auth, dialogue, monkeypatch):
    import app.api.routes.ai as routes

    async def fake_agent(history):
        return {
            "content": "Хвилинку, уточнюю деталі.",
            "iterations": 2,
            "tool_calls_history": [],
            "needs_approval": True,
            "proposed_booking": BOOKING,
            "intent": "booking",
        }

    monkeypatch.setattr(routes, "run_agent", fake_agent)
    body = client.post(url(dialogue, "respond"), headers=auth).json()
    assert body["content"] == "Хвилинку, уточнюю деталі."  # чернетка AI лишається як є
    assert body["suggested_message"] == CONFIRMATION
    assert body["suggested_message"].startswith("Вас записано на")


def test_pending_includes_suggested_message(client, auth, db_session, dialogue):
    seed(db_session, dialogue)
    got = client.get(url(dialogue, "pending"), headers=auth).json()["suggestion"]
    assert got["suggested_message"] == CONFIRMATION
    assert got["content"] == "Хвилинку, уточнюю деталі."


def test_respond_includes_suggested_message_for_question(client, auth, dialogue):
    body = client.post(url(dialogue, "respond"), headers=auth).json()
    assert body["proposed_booking"] is None
    assert body["suggested_message"] == body["content"]
    pending = client.get(url(dialogue, "pending"), headers=auth).json()["suggestion"]
    assert pending["suggested_message"] == body["content"]


def test_approve_sends_what_pending_suggested(client, auth, db_session, dialogue):
    seed(db_session, dialogue)
    shown = client.get(url(dialogue, "pending"), headers=auth).json()["suggestion"]
    client.post(url(dialogue, f"{shown['uuid']}/approve"), headers=auth, json={})
    assert last_outbound(db_session, dialogue).content == shown["suggested_message"]
