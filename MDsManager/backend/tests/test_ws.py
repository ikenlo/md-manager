from datetime import timedelta

import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.api.routes import ws as ws_route
from app.config import get_settings
from app.models import MediaAsset, Message, OutboundQueue
from app.models.base import utcnow
from app.services.adapters.mock import MockMetaAdapter
from app.services.outbound_worker import OutboundWorker
from app.services.ws_manager import manager


def token_of(auth: dict) -> str:
    return auth["Authorization"].removeprefix("Bearer ")


def next_of_type(ws, type_: str, limit: int = 5) -> dict:
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == type_:
            return msg
    raise AssertionError(f"no {type_}")


@pytest.fixture
def media_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "media_dir", (tmp_path / "media").as_posix())
    return tmp_path / "media"


def test_ws_rejects_bad_token(client):
    # close() до accept(): рукостискання не відбувається, код закриття 1008 (policy violation)
    for url in ("ws://localhost/api/ws", "ws://localhost/api/ws?token=nope"):
        with pytest.raises(WebSocketDisconnect) as e, client.websocket_connect(url):
            pass
        assert e.value.code == 1008


def test_ws_ping_pong_and_cleanup(client, auth):
    with client.websocket_connect(f"ws://localhost/api/ws?token={token_of(auth)}") as ws:
        assert manager.count() == 1
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
    client.get("/api/auth/me", headers=auth)  # дати серверу обробити disconnect
    assert manager.count() == 0


def test_ws_closes_when_session_revoked(client, auth, monkeypatch):
    monkeypatch.setattr(ws_route, "PING_SECONDS", 0.05)
    with client.websocket_connect(f"ws://localhost/api/ws?token={token_of(auth)}") as ws:
        assert ws.receive_json() == {"type": "ping"}
        assert client.post("/api/auth/logout", headers=auth).status_code == 204
        with pytest.raises(WebSocketDisconnect) as e:
            for _ in range(5):
                ws.receive_json()
        assert e.value.code == 1008


def test_post_message_and_worker_status_reach_ws(client, auth, session_factory):
    d = client.get("/api/dialogues", headers=auth, params={"channel": "instagram"}).json()["items"][
        0
    ]
    with client.websocket_connect(f"ws://localhost/api/ws?token={token_of(auth)}") as ws:
        sent = client.post(
            f"/api/dialogues/{d['uuid']}/messages", headers=auth, json={"text": "Вітаю"}
        ).json()
        ev = next_of_type(ws, "new_message")
        assert ev["dialogue_uuid"] == d["uuid"] and ev["message"]["uuid"] == sent["uuid"]
        assert ev["message"]["status"] == "queued"

        worker = OutboundWorker(
            session_factory=session_factory, adapter_factory=lambda: MockMetaAdapter(send_delay=0)
        )
        client.portal.call(worker.process_once)  # у тому ж event loop, що й сокет
        ev = next_of_type(ws, "message_status")
        assert ev["message_uuid"] == sent["uuid"] and ev["status"] == "sent"
        assert ev["external_id"].startswith("mock_")


def test_two_connections_both_receive(client, auth):
    tok = token_of(auth)
    with (
        client.websocket_connect(f"ws://localhost/api/ws?token={tok}") as a,
        client.websocket_connect(f"ws://localhost/api/ws?token={tok}") as b,
    ):
        r = client.post(
            "/api/_test/simulate_inbound",
            headers=auth,
            json={"client_name": "Оксана", "username": "oksana", "text": "Привіт!"},
        )
        assert r.status_code == 201
        for ws in (a, b):
            ev = next_of_type(ws, "new_message")
            assert ev["dialogue_uuid"] == r.json()["dialogue_uuid"]
            assert ev["dialogue"]["client"]["name"] == "Оксана"
            assert ev["dialogue"]["unread_count"] == 1
            upd = next_of_type(ws, "dialogue_updated")
            assert upd["unread_count"] == 1


def test_simulate_inbound_creates_dialogue(client, auth, db_session):
    r = client.post(
        "/api/_test/simulate_inbound",
        headers=auth,
        json={"client_name": "Ліна", "username": "@lina", "text": "Є час?", "channel": "facebook"},
    )
    assert r.status_code == 201
    items = client.get("/api/dialogues", headers=auth).json()["items"]
    d = next(i for i in items if i["uuid"] == r.json()["dialogue_uuid"])
    assert (
        d["status"] == "new"
        and d["unread_count"] == 1
        and d["channel"]["channel_type"] == "facebook"
    )
    assert d["last_message"]["direction"] == "inbound" and d["last_inbound_at"]
    msg = db_session.scalar(select(Message).where(Message.uuid == r.json()["message_uuid"]))
    assert msg.external_id.startswith("mock_msg_")
    client_row = msg.dialogue.client
    assert client_row.meta_fb_user_id.startswith("mock_fb_") and client_row.is_anonymous
    assert client_row.username == "lina"


def test_simulate_attachment_saves_and_serves_file(client, auth, db_session, media_dir):
    d = client.get("/api/dialogues", headers=auth).json()["items"][0]
    r = client.post(
        "/api/_test/simulate_attachment", headers=auth, json={"dialogue_uuid": d["uuid"]}
    )
    assert r.status_code == 201
    url = r.json()["attachment_url"]
    asset = db_session.scalar(select(MediaAsset))
    assert url == f"/api/media/{asset.uuid}" and asset.mime_type == "image/jpeg"
    assert (media_dir / asset.file_path).is_file()
    msgs = client.get(f"/api/dialogues/{d['uuid']}/messages", headers=auth).json()
    att = next(m for m in msgs if m["uuid"] == r.json()["message_uuid"])["attachments"]
    assert att[-1]["url"] == url and att[-1]["type"] == "image/jpeg"

    img = client.get(url)
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert img.content[:2] == b"\xff\xd8"


def test_media_404_and_no_traversal(client, db_session, media_dir):
    assert client.get("/api/media/nope").status_code == 404
    from app.models import Dialogue

    d = db_session.scalar(select(Dialogue))
    db_session.add(
        MediaAsset(
            dialogue_id=d.id, file_path="../../etc/passwd", mime_type="text/plain", file_size=1
        )
    )
    db_session.commit()
    bad = db_session.scalar(select(MediaAsset))
    assert client.get(f"/api/media/{bad.uuid}").status_code == 404


def test_trigger_failure_ends_failed(client, auth, db_session, session_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_outbound_retries", 2)
    d = client.get("/api/dialogues", headers=auth, params={"channel": "instagram"}).json()["items"][
        0
    ]
    r = client.post(
        "/api/_test/trigger_outbound_failure", headers=auth, json={"dialogue_uuid": d["uuid"]}
    )
    assert r.status_code == 201
    worker = OutboundWorker(
        session_factory=session_factory, adapter_factory=lambda: MockMetaAdapter(send_delay=0)
    )
    q = db_session.scalar(select(OutboundQueue).where(OutboundQueue.uuid == r.json()["queue_uuid"]))
    with client.websocket_connect(f"ws://localhost/api/ws?token={token_of(auth)}") as ws:
        client.portal.call(worker.process_once)
        db_session.expire_all()
        assert q.attempts == 1 and q.status == "pending" and "mock failure" in q.last_error
        q.next_retry_at = utcnow() - timedelta(seconds=1)
        db_session.commit()
        client.portal.call(worker.process_once)
        ev = next_of_type(ws, "message_status")
        assert ev["status"] == "failed" and ev["message_uuid"] == r.json()["message_uuid"]
    db_session.expire_all()
    assert q.status == "failed" and q.message.status == "failed"
    assert q.message.content.startswith("__FAIL__")


def test_test_endpoints_require_auth(client):
    assert client.post("/api/_test/simulate_inbound", json={}).status_code == 401


def test_test_endpoints_not_mounted_in_production(monkeypatch):
    from app.main import create_app

    monkeypatch.setattr(get_settings(), "app_env", "production")
    paths = {getattr(r, "path", "") for r in create_app().routes}
    assert "/api/_test/simulate_inbound" not in paths and "/api/ws" in paths


def test_dialogue_list_exposes_dispatcher_fields(client, auth):
    d = client.get("/api/dialogues", headers=auth).json()["items"][0]
    assert {"unread_count", "last_inbound_at", "webhook_status", "ai_active"} <= d.keys()
    assert d["ai_active"] is True and d["webhook_status"] == "inactive"
