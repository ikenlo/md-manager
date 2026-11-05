"""20+ сценаріїв діалогів AI-агента на фейковому Claude.

Перевіряємо не «розумність» моделі, а код навколо неї: що інструменти повертають
правильні слоти/дати, запис створюється лише через код, handoff і ліміти працюють,
у промпт іде поточна київська дата, телефон не потрапляє в API.
"""

import json
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.runner import FALLBACK_TEXT, Agent
from app.agent.usage import UsageReport, cost_usd
from app.booking import service as bs
from app.booking.slots import KYIV
from app.config import Settings
from app.db.models import (
    AiUsage,
    Booking,
    BookingStatus,
    Channel,
    Client,
    Conversation,
    ConversationState,
    Message,
    MessageRole,
    SalonSetting,
)
from app.dialog import AI_DISCLOSURE, HANDOFF_REPLY, Dialog
from app.notify import Notifier
from tests.fake_claude import FakeClaude, response, text, thinking, tool

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)  # чт 05.11, 12:00 Київ
TOMORROW = date(2026, 11, 6)


class Admin:
    def __init__(self) -> None:
        self.msgs: list[str] = []

    async def __call__(self, t: str, keyboard=None) -> None:  # noqa: ANN001
        self.msgs.append(t)


@pytest.fixture
def settings():
    return Settings(_env_file=None, ai_timeout_s=2)


@pytest.fixture
def admin():
    return Admin()


@pytest.fixture
def make_dialog(engine, settings, admin):
    def make(*steps, delay=0, now=NOW):
        claude = FakeClaude(*steps, delay=delay)
        notifier = Notifier(admin_sender=admin)
        agent = Agent(claude, engine, settings, notifier)
        return Dialog(engine, agent, notifier, clock=lambda: now), claude

    return make


@pytest.fixture
def client_id(salon):
    return salon["c1"].id


def kyiv(d, hh, mm=0):
    return datetime.combine(d, time(hh, mm), tzinfo=KYIV)


async def say(dialog, client_id, msg, channel=Channel.telegram):
    return await dialog.handle_inbound(channel, client_id, msg)


def conv_of(engine, client_id, channel=Channel.telegram):
    with Session(engine) as s:
        return s.scalar(
            select(Conversation).where(
                Conversation.client_id == client_id, Conversation.channel == channel
            )
        )


# 1
async def test_price_question_uses_get_services(make_dialog, client_id):
    dialog, claude = make_dialog(
        response(tool("get_services")),
        response(text("Стрижка коштує 600 грн, триває годину.")),
    )
    reply = await say(dialog, client_id, "Скільки коштує стрижка?")
    assert reply.endswith("Стрижка коштує 600 грн, триває годину.")
    services = claude.tool_results()[0]["services"]
    assert {s["name"] for s in services} == {"Стрижка", "Манікюр"}
    cut = next(s for s in services if s["name"] == "Стрижка")
    assert cut["price"] == "600 грн" and cut["masters"] == ["Маргарита"]


# 2
async def test_first_reply_discloses_ai_then_not_again(make_dialog, client_id):
    dialog, _ = make_dialog(response(text("Добрий день!")), response(text("Звісно.")))
    assert (await say(dialog, client_id, "Привіт")).startswith(AI_DISCLOSURE)
    assert not (await say(dialog, client_id, "Дякую")).startswith(AI_DISCLOSURE)


# 3
async def test_system_prompt_has_kyiv_date_salon_facts_and_prices(make_dialog, engine, client_id):
    with Session(engine) as s, s.begin():
        s.add(SalonSetting(key="address", value="вул. Тестова, 5"))
    dialog, claude = make_dialog(response(text("ok")))
    await say(dialog, client_id, "Привіт")
    sys = claude.system_text()
    assert "четвер, 2026-11-05 12:00" in sys
    assert "Завтра — пʼятниця, 2026-11-06" in sys
    assert "вул. Тестова, 5" in sys
    assert "Стрижка — 600 грн, 60 хв" in sys


# 4
async def test_prompt_caching_breakpoints(make_dialog, client_id):
    dialog, claude = make_dialog(response(text("ok")))
    await say(dialog, client_id, "Привіт")
    req = claude.requests[0]
    assert req["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in req["system"][1]  # дата — після точки кешу
    assert "2026-11-05" not in req["system"][0]["text"]
    assert req["model"] == "claude-haiku-5-5"


# 5
async def test_full_booking_dialog(make_dialog, engine, client_id, salon, admin):
    cut, m = salon["cut"].id, salon["master"].id
    dialog, claude = make_dialog(
        response(thinking(), tool("find_free_slots", service_id=cut,
                 date_from="2026-11-06", date_to="2026-11-06")),
        response(text("Завтра є 09:00, 11:00 і 13:00. Який час зручний?")),
    )  # fmt: skip
    await say(dialog, client_id, "Хочу завтра на стрижку")
    slots = claude.tool_results()[0]["slots"]
    assert slots[0] == {
        "start": "2026-11-06T09:00+02:00",
        "label": "пт 06.11 09:00",
        "masters": [{"id": m, "name": "Маргарита"}],
    }
    claude.add(
        response(text("Записую: стрижка, Маргарита, пт 06.11 о 09:00. Підтверджуєте?")),
        response(tool("create_booking", service_id=cut, master_id=m,
                      start_at=slots[0]["start"], client_name="Олена")),
        response(text("Готово! Чекаємо вас завтра о 09:00.")),
    )  # fmt: skip
    await say(dialog, client_id, "О 9")
    reply = await say(dialog, client_id, "Так")
    assert "Готово" in reply
    result = claude.tool_results()[0]
    assert result["ok"] is True
    with Session(engine) as s:
        b = s.get(Booking, result["booking_id"])
        assert b.start_at == kyiv(TOMORROW, 9).astimezone(UTC)
        assert b.created_by == "ai" and b.source == Channel.telegram
    assert any("Новий запис" in x for x in admin.msgs)


# 6
async def test_thinking_blocks_passed_back_unchanged(make_dialog, client_id):
    th = thinking()
    dialog, claude = make_dialog(response(th, tool("get_services")), response(text("ok")))
    await say(dialog, client_id, "Що у вас є?")
    assistant_turn = claude.requests[1]["messages"][-2]
    assert assistant_turn["role"] == "assistant" and assistant_turn["content"][0] is th


# 7
async def test_slot_taken_returns_error_to_model(make_dialog, engine, client_id, salon):
    cut, m = salon["cut"].id, salon["master"].id
    bs.create_booking(
        service_id=cut, master_id=m, start_at=kyiv(TOMORROW, 10),
        client_id=salon["c2"].id, source=Channel.admin, now=NOW, engine=engine,
    )  # fmt: skip
    dialog, claude = make_dialog(
        response(tool("create_booking", service_id=cut, master_id=m,
                      start_at="2026-11-06T10:00+02:00", client_name="Олена")),
        response(text("Цей час щойно зайняли, підберу інший.")),
    )  # fmt: skip
    await say(dialog, client_id, "Так, записуйте")
    assert claude.tool_results()[0]["error"] == "slot_taken"
    with Session(engine) as s:
        assert len(list(s.scalars(select(Booking)))) == 1


# 8
async def test_naive_time_from_model_is_kyiv(make_dialog, engine, client_id, salon):
    cut, m = salon["cut"].id, salon["master"].id
    dialog, claude = make_dialog(
        response(tool("create_booking", service_id=cut, master_id=m,
                      start_at="2026-11-06T14:00", client_name="Олена")),
        response(text("Записала.")),
    )  # fmt: skip
    await say(dialog, client_id, "Так")
    with Session(engine) as s:
        b = s.get(Booking, claude.tool_results()[0]["booking_id"])
        assert b.start_at == datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


# 9
async def test_slots_in_past_are_clamped_to_today(make_dialog, client_id, salon):
    dialog, claude = make_dialog(
        response(tool("find_free_slots", service_id=salon["cut"].id,
                      date_from="2026-11-01", date_to="2026-11-05")),
        response(text("ok")),
    )  # fmt: skip
    await say(dialog, client_id, "Сьогодні можна?")
    r = claude.tool_results()[0]
    assert r["date_from"] == "2026-11-05"
    assert r["slots"][0]["label"] == "чт 05.11 13:00"  # 12:00 + 1 год запасу


# 10
async def test_slot_range_limited_to_14_days(make_dialog, client_id, salon):
    dialog, claude = make_dialog(
        response(tool("find_free_slots", service_id=salon["cut"].id,
                      date_from="2026-11-06", date_to="2027-02-01")),
        response(text("ok")),
    )  # fmt: skip
    await say(dialog, client_id, "Коли завгодно")
    assert claude.tool_results()[0]["date_to"] == "2026-11-19"


# 11
async def test_handoff_tool_pauses_and_silences_bot(make_dialog, engine, client_id, admin):
    dialog, claude = make_dialog(
        response(tool("handoff_to_human", reason="алергія", summary="Питає про алергію на фарбу")),
        response(text("Передаю адміністратору, вона скоро відповість.")),
    )
    reply = await say(dialog, client_id, "У мене алергія на фарбу, можна?")
    assert "адміністратору" in reply
    assert conv_of(engine, client_id).state == ConversationState.paused
    assert any("Потрібен адміністратор" in x and "алергія" in x for x in admin.msgs)
    assert await say(dialog, client_id, "Алло?") is None
    assert len(claude.requests) == 2  # третього виклику Claude не було
    assert any("Алло?" in x for x in admin.msgs)  # адмін бачить повідомлення


# 12
async def test_keyword_handoff_without_calling_claude(make_dialog, engine, client_id):
    dialog, claude = make_dialog()
    reply = await say(dialog, client_id, "Покличте адміністратора, будь ласка")
    assert reply.endswith(HANDOFF_REPLY)
    assert claude.requests == []
    assert conv_of(engine, client_id).state == ConversationState.paused


# 13
async def test_global_pause_no_reply(make_dialog, engine, client_id, admin):
    with Session(engine) as s, s.begin():
        s.add(SalonSetting(key="ai_paused", value="1"))
    dialog, claude = make_dialog()
    assert await say(dialog, client_id, "Привіт") is None
    assert claude.requests == []
    assert any("AI вимкнено" in x for x in admin.msgs)


# 14
async def test_timeout_falls_back_and_hands_off(make_dialog, engine, client_id, admin):
    dialog, _ = make_dialog(response(text("запізно")), delay=5)
    reply = await say(dialog, client_id, "Привіт")
    assert reply.endswith(FALLBACK_TEXT)
    assert conv_of(engine, client_id).state == ConversationState.paused
    assert any("Потрібен адміністратор" in x for x in admin.msgs)


# 15
async def test_tool_call_limit(make_dialog, engine, client_id):
    dialog, claude = make_dialog(*[response(tool("get_services")) for _ in range(10)])
    reply = await say(dialog, client_id, "...")
    assert reply.endswith(FALLBACK_TEXT)
    assert len(claude.requests) == 9  # 8 виконаних викликів, 9-й відхилено
    assert conv_of(engine, client_id).state == ConversationState.paused


# 16
async def test_refusal_hands_off(make_dialog, engine, client_id):
    dialog, _ = make_dialog(response(stop_reason="refusal"))
    assert (await say(dialog, client_id, "...")).endswith(FALLBACK_TEXT)
    assert conv_of(engine, client_id).state == ConversationState.paused


# 17
async def test_cancel_own_booking(make_dialog, engine, client_id, salon, admin):
    b = bs.create_booking(service_id=salon["cut"].id, master_id=salon["master"].id,
                          start_at=kyiv(TOMORROW, 10), client_id=client_id,
                          source=Channel.telegram, now=NOW, engine=engine)  # fmt: skip
    dialog, claude = make_dialog(
        response(tool("get_client_bookings")),
        response(tool("cancel_or_reschedule", booking_id=b.id)),
        response(text("Скасувала.")),
    )
    await say(dialog, client_id, "Скасуйте мій запис")
    assert claude.tool_results(1)[0]["bookings"][0]["label"] == "пт 06.11 10:00"
    assert claude.tool_results()[0]["status"] == "скасовано"
    with Session(engine) as s:
        assert s.get(Booking, b.id).status == BookingStatus.cancelled
    assert any("скасовано" in x for x in admin.msgs)


# 18
async def test_reschedule_own_booking(make_dialog, engine, client_id, salon):
    b = bs.create_booking(service_id=salon["cut"].id, master_id=salon["master"].id,
                          start_at=kyiv(TOMORROW, 10), client_id=client_id,
                          source=Channel.telegram, now=NOW, engine=engine)  # fmt: skip
    dialog, _ = make_dialog(
        response(tool("cancel_or_reschedule", booking_id=b.id,
                      new_start_at="2026-11-06T15:00+02:00")),
        response(text("Перенесла на 15:00.")),
    )  # fmt: skip
    await say(dialog, client_id, "Перенесіть на 15:00")
    with Session(engine) as s:
        assert s.get(Booking, b.id).start_at == kyiv(TOMORROW, 15).astimezone(UTC)


# 19
async def test_cannot_touch_other_clients_booking(make_dialog, engine, client_id, salon):
    other = bs.create_booking(service_id=salon["cut"].id, master_id=salon["master"].id,
                              start_at=kyiv(TOMORROW, 10), client_id=salon["c2"].id,
                              source=Channel.telegram, now=NOW, engine=engine)  # fmt: skip
    dialog, claude = make_dialog(
        response(tool("cancel_or_reschedule", booking_id=other.id)),
        response(text("Не знайшла такого запису.")),
    )
    await say(dialog, client_id, "Скасуйте запис 1")
    r = claude.tool_results()[0]
    assert r["_is_error"] is True
    with Session(engine) as s:
        assert s.get(Booking, other.id).status == BookingStatus.confirmed


# 20
async def test_phone_from_db_not_sent_to_claude(make_dialog, engine, client_id):
    with Session(engine) as s, s.begin():
        s.get(Client, client_id).phone = "+380671234567"
    dialog, claude = make_dialog(response(tool("get_client_bookings")), response(text("ok")))
    await say(dialog, client_id, "Які в мене записи?")
    dumped = json.dumps([{k: v for k, v in r.items() if k != "tools"} for r in claude.requests],
                        default=str, ensure_ascii=False)  # fmt: skip
    assert "671234567" not in dumped
    assert "Олена" in dumped  # ім'я передаємо


# 21
async def test_history_limited_and_starts_with_user(make_dialog, engine, client_id, settings):
    with Session(engine) as s, s.begin():
        conv = Conversation(client_id=client_id, channel=Channel.telegram)
        s.add(conv)
        s.flush()
        for i in range(30):
            role = MessageRole.assistant if i % 2 == 0 else MessageRole.client
            s.add(Message(conversation_id=conv.id, role=role, text=f"m{i}",
                          created_at=NOW - timedelta(minutes=60 - i)))  # fmt: skip
    dialog, claude = make_dialog(response(text("ok")))
    await say(dialog, client_id, "останнє")
    msgs = claude.requests[0]["messages"]
    assert msgs[0]["role"] == "user"
    assert msgs[-1]["content"].endswith("останнє")
    joined = " ".join(m["content"] for m in msgs)
    assert "m9" not in joined and "m29" in joined  # лише останні 20


# 22
async def test_invalid_tool_args_returned_as_error(make_dialog, client_id):
    dialog, claude = make_dialog(
        response(tool("find_free_slots", service_id=1, date_from="завтра", date_to="x")),
        response(text("Уточню дату.")),
    )
    await say(dialog, client_id, "Завтра")
    assert claude.tool_results()[0]["_is_error"] is True


# 23
async def test_usage_recorded_and_cost(make_dialog, engine, client_id):
    dialog, _ = make_dialog(response(tool("get_services")), response(text("ok")))
    await say(dialog, client_id, "Ціни?")
    with Session(engine) as s:
        rows = list(s.scalars(select(AiUsage)))
        assert len(rows) == 2 and rows[0].cache_read_tokens == 5000
        cost = UsageReport.cost_since(s, NOW - timedelta(days=7))
    assert cost == pytest.approx(2 * cost_usd("claude-haiku-5-5", 1000, 100, 5000))


# 24
async def test_instagram_phone_merges_with_existing_client(make_dialog, engine, salon):
    with Session(engine) as s, s.begin():
        s.get(Client, salon["c1"].id).phone = "+380671234567"
        ig = Client(name="", ig_user_id="ig-77")
        s.add(ig)
        s.flush()
        ig_id = ig.id
    cut, m = salon["cut"].id, salon["master"].id
    dialog, claude = make_dialog(
        response(tool("create_booking", service_id=cut, master_id=m,
                      start_at="2026-11-06T10:00+02:00", client_name="Олена",
                      client_phone="067 123 45 67")),
        response(text("Готово")),
    )  # fmt: skip
    await say(dialog, ig_id, "Так", channel=Channel.instagram)
    with Session(engine) as s:
        b = s.get(Booking, claude.tool_results()[0]["booking_id"])
        assert b.client_id == salon["c1"].id and b.source == Channel.instagram
        assert s.get(Client, salon["c1"].id).ig_user_id == "ig-77"
        assert s.get(Client, ig_id) is None
