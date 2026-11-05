"""Telegram-бот і адмінка через справжній Dispatcher з фейковим Bot API."""

from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.booking import service as bs
from app.booking.slots import KYIV
from app.config import Settings
from app.db.models import (
    Booking,
    BookingStatus,
    Channel,
    Client,
    Conversation,
    ConversationState,
    SalonSetting,
    ScheduleException,
    Service,
)
from tests.tg_harness import ADMIN_CHAT, ADMIN_ID, CLIENT_ID, TG

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)  # чт 12:00 за Києвом
TOMORROW = date(2026, 11, 6)


@pytest.fixture
def settings():
    return Settings(
        _env_file=None, admin_ids=[ADMIN_ID], tg_admin_chat_id=ADMIN_CHAT, tg_bot_token="x"
    )


@pytest.fixture
def tg(engine, salon, settings):
    return TG(engine, settings, clock=lambda: NOW)


def kyiv(d, hh, mm=0):
    return datetime.combine(d, time(hh, mm), tzinfo=KYIV)


def make_booking(engine, salon, start, client="c1"):
    return bs.create_booking(
        service_id=salon["cut"].id,
        master_id=salon["master"].id,
        start_at=start,
        client_id=salon[client].id,
        source=Channel.telegram,
        now=NOW,
        engine=engine,
    )


# --- клієнт -----------------------------------------------------------------


async def test_start_greets_as_ai_and_registers_client(tg, engine):
    await tg.send("/start")
    assert "AI-помічник" in tg.last_text(CLIENT_ID)
    with Session(engine) as s:
        assert s.scalar(select(Client).where(Client.tg_user_id == CLIENT_ID)).name == "Олена"


async def test_client_books_via_buttons(tg, engine, salon):
    await tg.send("/book")
    await tg.press(tg.button("Стрижка"))
    # один майстер → одразу слоти; найближчий: сьогодні 13:00 (12:00 + 1 год запасу)
    first_slot = tg.buttons()[0]
    assert first_slot[0].startswith("чт 05.11 13:00")
    await tg.press(first_slot[1])
    assert "звертатися" in tg.last_text()
    await tg.send("Олена")
    assert "телефону" in tg.last_text()
    await tg.contact("+380671234567")
    assert "Записуємо?" in tg.last_text()
    await tg.press(tg.button("✅"))
    assert "Готово" in tg.last_text()
    with Session(engine) as s:
        b = s.scalar(select(Booking))
        assert b.start_at == kyiv(date(2026, 11, 5), 13).astimezone(UTC)
        assert b.client.tg_user_id == CLIENT_ID and b.client.phone == "+380671234567"
        assert b.source == Channel.telegram
    assert any("Новий запис" in m for m in tg.admin_msgs)


async def test_known_client_skips_name_and_phone(tg, engine, salon):
    with Session(engine) as s, s.begin():
        s.add(Client(name="Олена", phone="+380671111111", tg_user_id=CLIENT_ID))
    await tg.send("/book")
    await tg.press(tg.button("Стрижка"))
    await tg.press(tg.buttons()[0][1])
    assert "Записуємо?" in tg.last_text()


async def test_slot_taken_before_confirm_shows_slots_again(tg, engine, salon):
    await tg.send("/book")
    await tg.press(tg.button("Стрижка"))
    await tg.press(tg.buttons()[0][1])
    await tg.send("Олена")
    await tg.send("Пропустити")
    make_booking(engine, salon, kyiv(date(2026, 11, 5), 13), client="c2")  # хтось випередив
    await tg.press(tg.button("✅"))
    assert "щойно зайняли" in tg.last_text()
    assert not tg.buttons()[0][0].startswith("чт 05.11 13:00")
    with Session(engine) as s:
        assert len(list(s.scalars(select(Booking)))) == 1


async def test_bad_phone_is_asked_again(tg):
    await tg.send("/book")
    await tg.press(tg.button("Стрижка"))
    await tg.press(tg.buttons()[0][1])
    await tg.send("Олена")
    await tg.send("абв")
    assert "Не схоже на номер" in tg.last_text()


async def test_my_lists_and_cancels_booking(tg, engine, salon):
    with Session(engine) as s, s.begin():
        s.get(Client, salon["c1"].id).tg_user_id = CLIENT_ID
    b = make_booking(engine, salon, kyiv(TOMORROW, 10))
    await tg.send("/my")
    assert "пт 06.11 10:00" in tg.last_text()
    await tg.press(tg.button("✖️ Скасувати"))
    with Session(engine) as s:
        assert s.get(Booking, b.id).status == BookingStatus.cancelled
    assert any("скасував" in m for m in tg.admin_msgs)


async def test_free_text_without_agent_is_stored_and_admin_notified(tg, engine):
    await tg.send("Скільки коштує стрижка?")
    assert "Адміністратор скоро відповість" in tg.last_text()
    assert any("Нове повідомлення" in m for m in tg.admin_msgs)


# --- адмінка ----------------------------------------------------------------


async def test_admin_commands_ignored_for_non_admin(tg, engine, salon):
    make_booking(engine, salon, kyiv(TOMORROW, 10))
    await tg.send("/tomorrow", user_id=777, chat_id=ADMIN_CHAT)
    assert tg.texts(ADMIN_CHAT) == []


async def test_admin_commands_ignored_in_foreign_group(tg):
    await tg.send("/today", user_id=ADMIN_ID, chat_id=-999)
    assert tg.texts() == []


async def test_admin_day_schedule(tg, engine, salon):
    b = make_booking(engine, salon, kyiv(TOMORROW, 10))
    await tg.send("/tomorrow", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    text = tg.last_text(ADMIN_CHAT)
    assert "пʼятниця, 6 листопада" in text
    assert f"10:00–11:00 Стрижка — Олена [#{b.id}, TG]" in text
    await tg.send("/day 07.11", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "записів немає" in tg.last_text(ADMIN_CHAT)
    await tg.send("/day abc", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "⚠️" in tg.last_text(ADMIN_CHAT)


async def test_admin_cancel_notifies_client(tg, engine, salon):
    with Session(engine) as s, s.begin():
        s.get(Client, salon["c1"].id).tg_user_id = CLIENT_ID
    b = make_booking(engine, salon, kyiv(TOMORROW, 10))
    await tg.send(f"/cancel {b.id}", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "скасовано, клієнта повідомлено" in tg.last_text(ADMIN_CHAT)
    assert tg.client_msgs and "скасовано" in tg.client_msgs[0][1]


async def test_admin_cancel_reports_closed_channel(tg, engine, salon):
    b = make_booking(engine, salon, kyiv(TOMORROW, 10))  # у клієнта немає каналів
    await tg.send(f"/cancel {b.id}", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "канал закритий" in tg.last_text(ADMIN_CHAT)


async def test_admin_move(tg, engine, salon):
    b = make_booking(engine, salon, kyiv(TOMORROW, 10))
    other = make_booking(engine, salon, kyiv(TOMORROW, 14), client="c2")
    await tg.send(f"/move {b.id} 06.11 12:00", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "перенесено на пт 06.11 12:00" in tg.last_text(ADMIN_CHAT)
    await tg.send(f"/move {b.id} 06.11 14:00", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "зайнятий" in tg.last_text(ADMIN_CHAT)
    await tg.send("/move 12", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "Формат" in tg.last_text(ADMIN_CHAT)
    with Session(engine) as s:
        assert s.get(Booking, b.id).start_at == kyiv(TOMORROW, 12).astimezone(UTC)
        assert s.get(Booking, other.id).start_at == kyiv(TOMORROW, 14).astimezone(UTC)


async def test_admin_noshow_and_done(tg, engine, salon):
    a = make_booking(engine, salon, kyiv(TOMORROW, 10))
    b = make_booking(engine, salon, kyiv(TOMORROW, 14), client="c2")
    await tg.send(f"/noshow {a.id}", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    await tg.send(f"/done {b.id}", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    await tg.send(f"/done {b.id}", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "уже має статус" in tg.last_text(ADMIN_CHAT)
    with Session(engine) as s:
        assert s.get(Booking, a.id).status == BookingStatus.no_show
        assert s.get(Booking, b.id).status == BookingStatus.completed


async def test_admin_dayoff_warns_about_existing_bookings(tg, engine, salon):
    make_booking(engine, salon, kyiv(TOMORROW, 10))
    await tg.send("/dayoff марг 06.11", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    text = tg.last_text(ADMIN_CHAT)
    assert "Маргарита: вихідний" in text and "уже є записи" in text
    with Session(engine) as s:
        assert s.scalar(select(ScheduleException)).is_day_off
        assert bs.find_free_slots(s, salon["cut"].id, TOMORROW, TOMORROW, now=NOW) == []
    await tg.send("/dayoff Хтось 06.11", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "не знайдено" in tg.last_text(ADMIN_CHAT)


async def test_admin_manual_booking(tg, engine, salon):
    await tg.send("/book", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    await tg.press(tg.button("Стрижка"), user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    # адмін бачить слоти без запасу в 1 год: 12:00 сьогодні
    assert tg.buttons()[0][0].startswith("чт 05.11 12:00")
    await tg.press(tg.buttons()[0][1], user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    await tg.send("Ірина Нова", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    await tg.send("Пропустити", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "Не схоже на номер" in tg.last_text(ADMIN_CHAT)  # адміну телефон обов'язковий
    await tg.send("050 111 22 33", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    await tg.press(tg.button("✅"), user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "Записано #" in tg.last_text(ADMIN_CHAT)
    with Session(engine) as s:
        b = s.scalar(select(Booking))
        assert b.source == Channel.admin and b.created_by == str(ADMIN_ID)
        assert b.client.phone == "+380501112233" and b.client.name == "Ірина Нова"


async def test_admin_takeover_resume_reply(tg, engine, salon):
    with Session(engine) as s, s.begin():
        s.get(Client, salon["c1"].id).tg_user_id = CLIENT_ID
        conv = Conversation(client_id=salon["c1"].id, channel=Channel.telegram)
        s.add(conv)
        s.flush()
        conv_id = conv.id
    await tg.send(f"/takeover {conv_id}", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    with Session(engine) as s:
        assert s.get(Conversation, conv_id).state == ConversationState.paused
    await tg.send(f"/resume {conv_id}", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    with Session(engine) as s:
        assert s.get(Conversation, conv_id).state == ConversationState.ai
    await tg.send(
        f"/reply {conv_id} Добрий день! Так, можемо", user_id=ADMIN_ID, chat_id=ADMIN_CHAT
    )
    assert tg.client_msgs == [(str(CLIENT_ID), "Добрий день! Так, можемо")]
    with Session(engine) as s:
        c = s.get(Conversation, conv_id)
        assert c.state == ConversationState.paused
        assert c.messages[-1].text == "Добрий день! Так, можемо"
    await tg.press(f"cv:resume:{conv_id}", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    with Session(engine) as s:
        assert s.get(Conversation, conv_id).state == ConversationState.ai


async def test_admin_pause_all(tg, engine):
    await tg.send("/pause_all", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    with Session(engine) as s:
        assert s.get(SalonSetting, "ai_paused").value == "1"
    await tg.send("/resume_all", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    with Session(engine) as s:
        assert s.get(SalonSetting, "ai_paused").value == "0"


async def test_admin_price_edit(tg, engine, salon):
    await tg.send("/price", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "Стрижка — 600 грн, 60 хв" in tg.last_text(ADMIN_CHAT)
    await tg.press(tg.button("✏️ Стрижка"), user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    await tg.send("650-900", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    with Session(engine) as s:
        svc = s.get(Service, salon["cut"].id)
        assert (svc.price_from, svc.price_to) == (650, 900)


async def test_admin_client_card_and_forget(tg, engine, salon):
    with Session(engine) as s, s.begin():
        s.get(Client, salon["c1"].id).phone = "+380671234567"
    make_booking(engine, salon, kyiv(TOMORROW, 10))
    await tg.send("/client 067 123 45 67", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    text = tg.last_text(ADMIN_CHAT)
    assert "Олена" in text and "Майбутні записи" in text
    await tg.send("/forget 0671234567", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    with Session(engine) as s:
        assert s.get(Client, salon["c1"].id) is None
        assert s.scalar(select(Booking)) is None


async def test_admin_stats(tg, engine, salon):
    make_booking(engine, salon, kyiv(TOMORROW, 10))
    await tg.send("/stats", user_id=ADMIN_ID, chat_id=ADMIN_CHAT)
    assert "Нових записів: 1" in tg.last_text(ADMIN_CHAT)
