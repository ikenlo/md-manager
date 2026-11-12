import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Channel, CrmClient, Dialogue, Message, OutboundQueue
from app.models.base import utcnow
from app.services.adapters.mock import MockMetaAdapter
from app.services.events import MESSAGE_STATUS, NEW_MESSAGE, EventBus, events
from app.services.outbound_worker import OutboundWorker


class FakeAdapter(MockMetaAdapter):
    """Mock без затримки; рахує виклики; може падати."""

    def __init__(self, fail: bool = False) -> None:
        super().__init__(send_delay=0)
        self.fail = fail
        self.calls: list[tuple[str, str, str]] = []

    async def send_message(self, recipient_id, text, channel):
        self.calls.append((recipient_id, text, channel))
        if self.fail:
            raise ConnectionError("Meta недоступна")
        return await super().send_message(recipient_id, text, channel)


def make_queued(db, *, channel_type="instagram", ig_id="ig-1", status="queued", text="Вітаю"):
    ch = Channel(channel_type=channel_type, account_name="@md", status="mock")
    client = CrmClient(name="Олена", meta_ig_user_id=ig_id)
    d = Dialogue(client=client, channel=ch, status="in_progress", last_message_at=utcnow())
    msg = Message(
        dialogue=d, sender_type="human", content=text, direction="outbound", status=status
    )
    db.add_all([d, msg])
    db.flush()
    q = OutboundQueue(message_id=msg.id, status="pending", next_retry_at=utcnow())
    db.add(q)
    db.commit()
    return d, msg, q


def worker_for(session_factory, adapter, bus=None):
    return OutboundWorker(
        session_factory=session_factory, adapter_factory=lambda: adapter, bus=bus or EventBus()
    )


def run(worker):
    return asyncio.run(worker.process_once())


def test_worker_processes_pending_queue(db_session, session_factory):
    d, msg, q = make_queued(db_session)
    bus, seen = EventBus(), []

    async def on(event_type, payload):
        seen.append((event_type, payload))

    bus.subscribe(on)
    adapter = FakeAdapter()
    stats = run(worker_for(session_factory, adapter, bus))

    assert {k: stats[k] for k in ("processed", "sent", "failed")} == {
        "processed": 1,
        "sent": 1,
        "failed": 0,
    }
    assert adapter.calls == [("ig-1", "Вітаю", "instagram")]
    db_session.expire_all()
    assert msg.status == "sent" and msg.external_id.startswith("mock_")
    assert q.status == "sent" and q.attempts == 0
    assert d.last_outbound_at is not None
    assert seen == [
        (
            MESSAGE_STATUS,
            {
                "message_uuid": msg.uuid,
                "dialogue_uuid": d.uuid,
                "status": "sent",
                "external_id": msg.external_id,
            },
        )
    ]


def test_worker_retries_on_failure(db_session, session_factory):
    _, msg, q = make_queued(db_session)
    worker = worker_for(session_factory, FakeAdapter(fail=True))
    max_retries = get_settings().max_outbound_retries

    before = utcnow()
    stats = run(worker)
    db_session.expire_all()
    assert stats["processed"] == 1 and stats["sent"] == 0 and stats["failed"] == 0
    assert q.attempts == 1 and q.status == "pending" and msg.status == "queued"
    assert "ConnectionError" in q.last_error
    assert q.next_retry_at >= before + timedelta(seconds=60)

    # ще не час — воркер не чіпає
    assert run(worker)["processed"] == 0

    for attempt in range(2, max_retries + 1):
        q.next_retry_at = utcnow() - timedelta(seconds=1)
        db_session.commit()
        run(worker)
        db_session.expire_all()
        assert q.attempts == attempt
        if attempt < max_retries:
            assert q.status == "pending"
            assert q.next_retry_at > utcnow() + timedelta(seconds=60 * attempt - 5)

    assert q.status == "failed" and msg.status == "failed"
    q.next_retry_at = utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert run(worker)["processed"] == 0  # failed більше не беремо


def test_worker_skips_already_sent(db_session, session_factory):
    _, msg, q = make_queued(db_session, status="sent")
    adapter = FakeAdapter()
    stats = run(worker_for(session_factory, adapter))
    db_session.expire_all()
    assert adapter.calls == []
    assert q.status == "sent" and msg.status == "sent"
    assert stats["sent"] == 1


def test_worker_fails_without_recipient(db_session, session_factory):
    _, msg, q = make_queued(db_session, ig_id=None)
    adapter = FakeAdapter()
    stats = run(worker_for(session_factory, adapter))
    db_session.expire_all()
    assert adapter.calls == []
    assert q.status == "failed" and q.last_error == "no recipient id" and msg.status == "failed"
    assert stats["failed"] == 1


def test_worker_uses_fb_id_for_facebook(db_session, session_factory):
    d, _, _ = make_queued(db_session, channel_type="facebook", ig_id="ig-wrong")
    d.client.meta_fb_user_id = "fb-7"
    db_session.commit()
    adapter = FakeAdapter()
    run(worker_for(session_factory, adapter))
    assert adapter.calls[0][0] == "fb-7" and adapter.calls[0][2] == "facebook"


def test_worker_ignores_not_due_and_orders_by_created(db_session, session_factory):
    make_queued(db_session, ig_id="ig-a", text="перше")
    _, _, q2 = make_queued(db_session, ig_id="ig-b", text="друге")
    make_queued(db_session, ig_id="ig-c", text="третє")
    q2.next_retry_at = utcnow() + timedelta(minutes=5)
    db_session.commit()
    adapter = FakeAdapter()
    stats = run(worker_for(session_factory, adapter))
    assert [c[1] for c in adapter.calls] == ["перше", "третє"]
    assert stats["processed"] == 2


def test_post_message_creates_queue_entry(client, auth, db_session):
    seen = []

    async def on(event_type, payload):
        seen.append((event_type, payload))

    unsubscribe = events.subscribe(on)
    try:
        d = client.get("/api/dialogues", headers=auth, params={"status": "new"}).json()["items"][0]
        r = client.post(
            f"/api/dialogues/{d['uuid']}/messages", headers=auth, json={"text": "  Добрий день!  "}
        )
    finally:
        unsubscribe()
    assert r.status_code == 201
    body = r.json()
    assert body["content"] == "Добрий день!"
    assert (
        body["status"] == "queued"
        and body["direction"] == "outbound"
        and body["sender_type"] == "human"
    )
    assert {"id", "uuid", "created_at"} <= body.keys()

    msg = db_session.scalar(select(Message).where(Message.uuid == body["uuid"]))
    q = db_session.scalar(select(OutboundQueue).where(OutboundQueue.message_id == msg.id))
    assert q.status == "pending" and q.attempts == 0
    dlg = db_session.scalar(select(Dialogue).where(Dialogue.uuid == d["uuid"]))
    assert dlg.last_message_at == msg.created_at
    assert dlg.last_outbound_at is None and dlg.status == "in_progress"
    assert seen == [(NEW_MESSAGE, {"dialogue_uuid": d["uuid"], "message": body})]


@pytest.mark.parametrize("text", ["", "   "])
def test_post_message_empty_text(client, auth, text):
    d = client.get("/api/dialogues", headers=auth).json()["items"][0]
    r = client.post(f"/api/dialogues/{d['uuid']}/messages", headers=auth, json={"text": text})
    assert r.status_code == 400


def test_post_message_unknown_dialogue(client, auth):
    r = client.post(
        "/api/dialogues/00000000-0000-0000-0000-000000000000/messages",
        headers=auth,
        json={"text": "Привіт"},
    )
    assert r.status_code == 404


def test_post_then_worker_sends(client, auth, db_session, session_factory):
    d = client.get("/api/dialogues", headers=auth, params={"channel": "instagram"}).json()["items"][
        0
    ]
    uuid = client.post(
        f"/api/dialogues/{d['uuid']}/messages", headers=auth, json={"text": "Так"}
    ).json()["uuid"]
    run(worker_for(session_factory, FakeAdapter()))
    msgs = client.get(f"/api/dialogues/{d['uuid']}/messages", headers=auth).json()
    assert next(m for m in msgs if m["uuid"] == uuid)["status"] == "sent"


def test_event_bus_isolates_failing_subscriber():
    bus, got = EventBus(), []

    async def bad(*_):
        raise RuntimeError("boom")

    async def good(event_type, payload):
        got.append(payload)

    bus.subscribe(bad)
    bus.subscribe(good)
    asyncio.run(bus.emit("x", {"a": 1}))
    assert got == [{"a": 1}]


def test_scheduler_starts_and_stops_with_app(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    monkeypatch.setattr(get_settings(), "outbound_worker_enabled", True)
    app = create_app()
    with TestClient(app, base_url="http://localhost"):
        sched = app.state.scheduler
        assert sched.running and sched.get_job("outbound_worker") is not None
    assert not sched.running
