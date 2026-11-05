"""Instagram: вебхук, підпис, ехо, дублікати, вікно 24 год, відправка, токен."""

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.runner import Agent
from app.channels import instagram as ig
from app.config import Settings
from app.db.models import Client, Conversation, ConversationState, Message, SalonSetting
from app.dialog import Dialog
from app.notify import Notifier
from app.scheduler import Jobs
from tests.fake_claude import FakeClaude, response, text

SECRET = "app-secret"
OWN_ID = "17841400000000000"
NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)


def payload(*messaging):
    return {
        "object": "instagram",
        "entry": [{"id": OWN_ID, "time": 1, "messaging": list(messaging)}],
    }


def msg(sender="igsid-1", mid="m1", txt="Привіт", **extra):
    return {
        "sender": {"id": sender},
        "recipient": {"id": OWN_ID},
        "timestamp": 1,
        "message": {"mid": mid, "text": txt, **extra},
    }


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def settings():
    return Settings(_env_file=None, ig_app_secret=SECRET, ig_verify_token="vt",
                    ig_access_token="tok-env")  # fmt: skip


class FakeGraph:
    def __init__(self, status=200):
        self.requests: list[httpx.Request] = []
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/refresh_access_token"):
            return httpx.Response(
                self.status, json={"access_token": "tok-new", "expires_in": 5184000}
            )
        return httpx.Response(self.status, json={"recipient_id": "x", "message_id": "y"})

    def sent(self):
        return [json.loads(r.content) for r in self.requests if r.method == "POST"]


@pytest.fixture
def graph():
    return FakeGraph()


@pytest.fixture
def ig_client(engine, settings, graph):
    return ig.InstagramClient(
        engine, settings, httpx.AsyncClient(transport=httpx.MockTransport(graph))
    )


@pytest.fixture
def admin_msgs():
    return []


@pytest.fixture
def make_handler(engine, settings, ig_client, admin_msgs, salon):
    def make(*steps, now=NOW):
        async def admin(t, kb=None):  # noqa: ANN001
            admin_msgs.append(t)

        notifier = Notifier(admin_sender=admin)
        claude = FakeClaude(*steps)
        dialog = Dialog(engine, Agent(claude, engine, settings, notifier), notifier,
                        clock=lambda: now)  # fmt: skip
        return ig.InstagramHandler(engine, dialog, ig_client, notifier, clock=lambda: now), claude

    return make


# --- чисті функції ---------------------------------------------------------


def test_signature():
    body = b'{"a":1}'
    assert ig.check_signature(body, sign(body), SECRET)
    assert not ig.check_signature(body + b" ", sign(body), SECRET)
    assert not ig.check_signature(body, None, SECRET)
    assert not ig.check_signature(body, sign(body), "")


def test_parse_skips_echo_seen_and_own_messages():
    events = ig.parse_events(
        payload(
            msg(mid="a"),
            msg(sender=OWN_ID, mid="b", is_echo=True),
            {"sender": {"id": "igsid-1"}, "recipient": {"id": OWN_ID}, "read": {"mid": "a"}},
            {"sender": {"id": "igsid-1"}, "message": {"mid": "c", "is_deleted": True}},
            {"sender": {"id": "igsid-2"}, "message": {"mid": "d",
             "attachments": [{"type": "image", "payload": {"url": "u"}}]}},
        )
    )  # fmt: skip
    assert events == [
        ig.InboundText("igsid-1", "a", "Привіт"),
        ig.Deleted("c"),
        ig.InboundAttachment("igsid-2", "d", ("image",)),
    ]
    assert ig.parse_events({"object": "page", "entry": []}) == []


def test_split_text_respects_1000_bytes():
    long = ("слово " * 400).strip()  # ~4800 байт
    parts = ig.split_text(long)
    assert len(parts) > 1
    assert all(len(p.encode()) <= 1000 for p in parts)
    assert " ".join(parts) == long
    assert ig.split_text("коротко") == ["коротко"]


# --- HTTP вебхук -----------------------------------------------------------


def test_webhook_verify_and_signature(settings):
    received = []

    async def process(events):
        received.extend(events)

    app = FastAPI()
    app.include_router(ig.build_router(lambda: settings, process))
    c = TestClient(app)
    ok = c.get("/webhook/instagram", params={"hub.mode": "subscribe", "hub.verify_token": "vt",
                                             "hub.challenge": "12345"})  # fmt: skip
    assert ok.status_code == 200 and ok.text == "12345"
    bad = c.get("/webhook/instagram", params={"hub.mode": "subscribe", "hub.verify_token": "x",
                                              "hub.challenge": "1"})  # fmt: skip
    assert bad.status_code == 403

    body = json.dumps(payload(msg())).encode()
    assert c.post("/webhook/instagram", content=body).status_code == 403
    assert c.post("/webhook/instagram", content=body,
                  headers={"X-Hub-Signature-256": "sha256=00"}).status_code == 403  # fmt: skip
    r = c.post("/webhook/instagram", content=body, headers={"X-Hub-Signature-256": sign(body)})
    assert r.status_code == 200
    assert received == [ig.InboundText("igsid-1", "m1", "Привіт")]


# --- обробка подій ---------------------------------------------------------


async def test_inbound_text_gets_ai_reply_via_graph(make_handler, engine, graph):
    handler, claude = make_handler(response(text("Добрий день! Чим допомогти?")))
    await ig.process_events(handler, ig.parse_events(payload(msg())))
    (sent,) = graph.sent()
    assert sent["recipient"] == {"id": "igsid-1"}
    assert sent["message"]["text"].endswith("Добрий день! Чим допомогти?")
    assert "AI-помічник" in sent["message"]["text"]
    req = graph.requests[0]
    assert req.url.host == "graph.instagram.com" and req.url.path == "/v27.0/me/messages"
    assert req.headers["Authorization"] == "Bearer tok-env"
    assert "Instagram Direct" in claude.system_text()


async def test_duplicate_delivery_processed_once(make_handler, graph):
    handler, claude = make_handler(response(text("ok")))
    events = ig.parse_events(payload(msg(mid="dup")))
    await ig.process_events(handler, events)
    await ig.process_events(handler, events)
    assert len(claude.requests) == 1 and len(graph.sent()) == 1


async def test_deleted_message_removed(make_handler, engine):
    handler, _ = make_handler(response(text("ok")))
    await ig.process_events(handler, ig.parse_events(payload(msg(mid="del-me"))))
    await handler.handle(ig.Deleted("del-me"))
    with Session(engine) as s:
        assert s.scalar(select(Message).where(Message.external_id == "del-me")) is None


async def test_attachment_hands_off(make_handler, engine, graph, admin_msgs):
    handler, claude = make_handler()
    await handler.handle(ig.InboundAttachment("igsid-9", "att", ("image",)))
    assert claude.requests == []
    assert any("image" in m for m in admin_msgs)
    assert "адміністратору" in graph.sent()[0]["message"]["text"]
    with Session(engine) as s:
        conv = s.scalar(select(Conversation))
        assert conv.state == ConversationState.paused


async def test_send_failure_notifies_admin(engine, settings, make_handler, admin_msgs, graph):
    graph.status = 400
    handler, _ = make_handler(response(text("ok")))
    await ig.process_events(handler, ig.parse_events(payload(msg())))
    assert any("Не вдалося відповісти в Instagram" in m for m in admin_msgs)


async def test_window_closed_blocks_outbound_notify(engine, settings, ig_client, salon):
    with Session(engine) as s, s.begin():
        c = Client(name="Олена", ig_user_id="igsid-5")
        s.add(c)
        s.flush()
        s.add(Conversation(client_id=c.id, channel="instagram",
                           last_inbound_at=NOW - timedelta(hours=25)))  # fmt: skip
        cid = c.id
    notifier = Notifier(senders={ig.Channel.instagram: ig_client.send})
    with Session(engine) as s:
        assert notifier.client_channel(s, s.get(Client, cid), NOW) is None
        assert notifier.client_channel(s, s.get(Client, cid), NOW - timedelta(hours=2)) is not None


# --- токен -----------------------------------------------------------------


async def test_token_refresh_stored_and_used(engine, settings, ig_client, graph):
    jobs = Jobs(engine, settings, Notifier(), ig_client, clock=lambda: NOW)
    await jobs.refresh_ig_token()
    with Session(engine) as s:
        assert s.get(SalonSetting, ig.TOKEN_KEY).value == "tok-new"
    assert graph.requests[0].url.params["grant_type"] == "ig_refresh_token"
    assert ig_client.token() == "tok-new"
    await jobs.refresh_ig_token()  # щойно оновлено → не чіпаємо
    assert len(graph.requests) == 1
    jobs.clock = lambda: NOW + timedelta(days=8)
    await jobs.refresh_ig_token()
    assert len(graph.requests) == 2


async def test_token_refresh_failure_alerts_admin(engine, settings, ig_client, graph):
    graph.status = 400
    msgs = []

    async def admin(t, kb=None):  # noqa: ANN001
        msgs.append(t)

    await Jobs(engine, settings, Notifier(admin_sender=admin), ig_client,
               clock=lambda: NOW).refresh_ig_token()  # fmt: skip
    assert msgs and "токен Instagram" in msgs[0]


def test_background_tasks_kept_alive(settings):
    """Задача обробки не губиться збирачем сміття, поки виконується."""
    done = []

    async def process(events):
        await asyncio.sleep(0)
        done.append(events)

    router = ig.build_router(lambda: settings, process)
    app = FastAPI()
    app.include_router(router)
    body = json.dumps(payload(msg())).encode()
    with TestClient(app) as c:
        c.post("/webhook/instagram", content=body, headers={"X-Hub-Signature-256": sign(body)})
    assert done
