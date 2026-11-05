"""Режим MDS Connect: агент читає каталог і слоти з MDS і записує туди з атрибуцією."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.orm import Session

from app import marketing
from app.agent.runner import Agent
from app.channels import instagram as ig
from app.config import Settings
from app.db.models import Channel, Client, Conversation
from app.dialog import Dialog
from app.integrations.mds import MdsClient
from app.notify import Notifier
from tests.fake_claude import FakeClaude, response, text, tool
from tests.tg_harness import ADMIN_CHAT, ADMIN_ID, CLIENT_ID, TG

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)  # чт 12:00 Київ

CATALOG = {
    "services": [
        {
            "id": 6,
            "name": "Стрижка до плечей",
            "section": "Жіночі",
            "category": "Стрижка",
            "subcategory": None,
            "duration_min": 60,
            "price": 45000,
            "price_from": False,
            "master_ids": [3, 4],
        },
        {
            "id": 8,
            "name": "Довге волосся",
            "section": "Жіночі",
            "category": "Стрижка",
            "subcategory": None,
            "duration_min": 60,
            "price": 55000,
            "price_from": True,
            "master_ids": [3],
        },
    ],
    "masters": [{"id": 3, "name": "Олена"}, {"id": 4, "name": "Ірина"}],
}


class FakeMds:
    """Мінімальна імітація /api/ext/v1 MDS Connect."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []
        self.appts: dict[int, dict] = {}
        self.taken: set[str] = set()
        self.next_id = 100

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["X-MDS-Integration-Token"] == "tok"
        path = request.url.path.removeprefix("/api/ext/v1")
        body = json.loads(request.content) if request.content else {}
        self.calls.append((request.method, path, body or dict(request.url.params)))
        if path == "/catalog":
            return httpx.Response(200, json=CATALOG)
        if path == "/slots":
            return httpx.Response(
                200,
                json=[
                    {"starts_at": "2026-11-06T09:00", "master_ids": [3, 4]},
                    {"starts_at": "2026-11-06T09:30", "master_ids": [3]},
                    {"starts_at": "2026-11-06T14:00", "master_ids": [4]},
                ],
            )
        if path == "/appointments" and request.method == "POST":
            if body["starts_at"] in self.taken:
                return httpx.Response(
                    409, json={"error": "slot_taken", "detail": "Майстер зайнятий"}
                )
            self.taken.add(body["starts_at"])
            self.next_id += 1
            a = {
                "id": self.next_id,
                "status": "pending",
                "starts_at": body["starts_at"],
                "ends_at": body["starts_at"],
                "service_id": body["service_id"],
                "service_name": "Стрижка до плечей",
                "master_id": body["master_id"],
                "master_name": "Олена",
                "price": 45000,
                "source": body["channel"],
                "created": True,
                "_client": body["client"],
            }
            self.appts[a["id"]] = a
            return httpx.Response(200, json=a)
        if path == "/appointments/lookup":
            return httpx.Response(
                200, json=[a for a in self.appts.values() if a["status"] != "cancelled"]
            )
        if path.endswith("/cancel"):
            a = self.appts[int(path.split("/")[2])]
            a["status"] = "cancelled"
            return httpx.Response(200, json=a)
        if path == "/visits":
            return httpx.Response(
                200,
                json=[
                    {
                        "status": "completed",
                        "paid_amount": 50000,
                        "attribution": {"channel": "instagram", "lead_source": "ig_ad_1"},
                    },
                    {
                        "status": "completed",
                        "paid_amount": 45000,
                        "attribution": {"channel": "instagram", "lead_source": "ig_ad_1"},
                    },
                    {
                        "status": "no_show",
                        "paid_amount": None,
                        "attribution": {"channel": "telegram-ai", "lead_source": "tg_post"},
                    },
                    {
                        "status": "completed",
                        "paid_amount": 60000,
                        "attribution": None,
                        "client_source": "рекомендація",
                    },
                ],
            )
        if path == "/ad-spend":
            return httpx.Response(200, json={"total": 40000, "items": []})
        return httpx.Response(404, json={"error": "not_found"})


@pytest.fixture
def fake_mds():
    return FakeMds()


@pytest.fixture
def mds(fake_mds):
    return MdsClient(
        "https://mds.test", "tok", httpx.AsyncClient(transport=httpx.MockTransport(fake_mds))
    )


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        mds_url="https://mds.test",
        mds_token="tok",
        admin_ids=[ADMIN_ID],
        tg_admin_chat_id=ADMIN_CHAT,
        tg_bot_username="Manddmanagerbot",
    )


@pytest.fixture
def make_dialog(engine, settings, mds):
    admin = []

    async def admin_sender(t, kb=None):  # noqa: ANN001
        admin.append(t)

    def make(*steps):
        claude = FakeClaude(*steps)
        notifier = Notifier(admin_sender=admin_sender)
        agent = Agent(claude, engine, settings, notifier, mds=mds)
        return Dialog(engine, agent, notifier, clock=lambda: NOW), claude, admin

    return make


def _client(engine, **kw):
    with Session(engine) as s, s.begin():
        c = Client(name="Олена", **kw)
        s.add(c)
        s.flush()
        return c.id


async def test_services_and_slots_come_from_mds(make_dialog, engine):
    cid = _client(engine, tg_user_id=555)
    dialog, claude, _ = make_dialog(
        response(tool("get_services")),
        response(
            tool("find_free_slots", service_id=6, date_from="2026-11-06", date_to="2026-11-06")
        ),
        response(text("Є 09:00 і 14:00")),
    )
    await dialog.handle_inbound(Channel.telegram, cid, "Хочу стрижку завтра")
    svc = claude.tool_results(1)[0]["services"]
    assert svc[0] == {
        "id": 6,
        "name": "Стрижка до плечей",
        "category": "Жіночі / Стрижка",
        "price": "450 грн",
        "duration_min": 60,
        "masters": ["Олена", "Ірина"],
    }
    assert svc[1]["price"] == "від 550 грн"
    slots = claude.tool_results()[0]["slots"]
    assert [x["label"] for x in slots] == ["пт 06.11 09:00", "пт 06.11 09:30", "пт 06.11 14:00"]
    assert slots[0]["start"] == "2026-11-06T09:00+02:00"
    assert slots[0]["masters"] == [{"id": 3, "name": "Олена"}, {"id": 4, "name": "Ірина"}]


async def test_booking_goes_to_mds_with_attribution(make_dialog, engine, fake_mds):
    cid = _client(engine, tg_user_id=555, phone="+380671234567")
    with Session(engine) as s, s.begin():
        s.add(Conversation(client_id=cid, channel=Channel.telegram, lead_source="tg_post_1105"))
    dialog, claude, admin = make_dialog(
        response(tool("create_booking", service_id=6, master_id=3,
                      start_at="2026-11-06T09:00+02:00", client_name="Олена")),
        response(text("Записала!")),
    )  # fmt: skip
    await dialog.handle_inbound(Channel.telegram, cid, "Так, записуйте")
    res = claude.tool_results()[0]
    assert res["ok"] is True and res["status"] == "очікує підтвердження майстра"
    method, path, body = fake_mds.calls[-1]
    assert (method, path) == ("POST", "/appointments")
    assert body["channel"] == "telegram-ai"
    assert body["starts_at"] == "2026-11-06T09:00"  # київський час без зони, як у MDS
    assert body["client"] == {
        "name": "Олена",
        "phone": "+380671234567",
        "telegram_user_id": 555,
        "instagram_user_id": None,
    }
    assert body["attribution"] == {"lead_source": "tg_post_1105"}
    assert body["external_ref"].startswith("mdm-c")
    assert any("MDS Connect #101" in m for m in admin)


async def test_phone_required_for_mds_booking(make_dialog, engine):
    cid = _client(engine, ig_user_id="ig-9")
    dialog, claude, _ = make_dialog(
        response(tool("create_booking", service_id=6, master_id=3,
                      start_at="2026-11-06T09:00+02:00", client_name="Олена")),
        response(text("Напишіть, будь ласка, телефон")),
    )  # fmt: skip
    await dialog.handle_inbound(Channel.instagram, cid, "Записуйте")
    r = claude.tool_results()[0]
    assert r["_is_error"] and "телефону" in r["error"]


async def test_slot_taken_from_mds(make_dialog, engine, fake_mds):
    cid = _client(engine, tg_user_id=555, phone="+380671234567")
    fake_mds.taken.add("2026-11-06T09:00")
    dialog, claude, _ = make_dialog(
        response(tool("create_booking", service_id=6, master_id=3,
                      start_at="2026-11-06T09:00+02:00", client_name="Олена")),
        response(text("Цей час щойно зайняли")),
    )  # fmt: skip
    await dialog.handle_inbound(Channel.telegram, cid, "Так")
    assert claude.tool_results()[0]["error"] == "slot_taken"


async def test_reschedule_books_new_then_cancels_old(make_dialog, engine, fake_mds):
    cid = _client(engine, tg_user_id=555, phone="+380671234567")
    dialog, claude, _ = make_dialog(
        response(tool("create_booking", service_id=6, master_id=3,
                      start_at="2026-11-06T09:00+02:00", client_name="Олена")),
        response(text("ok")),
        response(tool("cancel_or_reschedule", booking_id=101,
                      new_start_at="2026-11-06T14:00+02:00")),
        response(text("Перенесла")),
    )  # fmt: skip
    await dialog.handle_inbound(Channel.telegram, cid, "Записуйте")
    await dialog.handle_inbound(Channel.telegram, cid, "Перенесіть на 14:00")
    assert claude.tool_results()[0]["status"] == "перенесено"
    assert (
        fake_mds.appts[101]["status"] == "cancelled" and fake_mds.appts[102]["status"] == "pending"
    )
    assert [c[1] for c in fake_mds.calls][-3:] == [
        "/appointments/lookup",
        "/appointments",
        "/appointments/101/cancel",
    ]


def test_marketing_aggregation():
    rows = marketing.aggregate_mds_visits(
        FakeMds()(
            httpx.Request(
                "GET", "https://x/api/ext/v1/visits", headers={"X-MDS-Integration-Token": "tok"}
            )
        ).json()
    )
    assert [(r.source, r.bookings, r.came, r.no_show, r.revenue_kop) for r in rows] == [
        ("ig_ad_1", 2, 2, 0, 95000),
        ("рекомендація", 1, 1, 0, 60000),
        ("tg_post", 1, 0, 1, 0),
    ]
    text_ = marketing.format_sources(rows, 30, 40000)
    assert "ig_ad_1: записів 2, прийшли 2, виручка 950 грн" in text_
    assert "Реклама (витрати в MDS): 400 грн" in text_
    assert "≈ 200 грн рекламних витрат на один візит з мітками" in text_


def test_instagram_ad_referral_becomes_lead_source():
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "own",
                "messaging": [
                    {
                        "sender": {"id": "u1"},
                        "message": {"mid": "m1", "text": "Скільки коштує?"},
                        "referral": {"ad_id": "120211", "source": "ADS", "type": "OPEN_THREAD"},
                    },
                    {
                        "sender": {"id": "u2"},
                        "message": {"mid": "m2", "text": "Привіт", "referral": {"ref": "bio_link"}},
                    },
                    {
                        "sender": {"id": "u3"},
                        "message": {"mid": "m3", "text": "Hi", "referral": {"ref": "bad ref!"}},
                    },
                ],
            }
        ],
    }
    assert [e.ref for e in ig.parse_events(payload)] == ["ig_ad_120211", "bio_link", None]


# --- Telegram ------------------------------------------------------------------


@pytest.fixture
def tg(engine, settings, mds):
    t = TG(engine, settings, clock=lambda: NOW)
    t.dp["mds"] = mds
    return t


async def test_start_with_label_sets_lead_source(tg, engine):
    await tg.send("/start ig_reels_1201")
    with Session(engine) as s:
        conv = s.query(Conversation).one()
        assert conv.lead_source == "ig_reels_1201"
    await tg.send("/start bad%label")
    with Session(engine) as s:
        assert s.query(Conversation).one().lead_source == "ig_reels_1201"


async def test_link_and_sources_commands(tg):
    await tg.send("/link ig_reels_1201", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "https://t.me/Manddmanagerbot?start=ig_reels_1201" in tg.last_text(ADMIN_CHAT)
    await tg.send("/link погана мітка", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "Формат" in tg.last_text(ADMIN_CHAT)
    await tg.send("/sources 7", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "Джерела записів за 7 днів" in tg.last_text(ADMIN_CHAT)
    assert "ig_ad_1" in tg.last_text(ADMIN_CHAT)


async def test_mds_mode_redirects_schedule_commands(tg):
    await tg.send("/today", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "MDS Connect" in tg.last_text(ADMIN_CHAT)
    await tg.send("/book")
    assert "підберу вільний час" in tg.last_text(CLIENT_ID)
