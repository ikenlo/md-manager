"""Нагадування, автоповернення AI, чистка історії."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import reminders as rm
from app.config import Settings
from app.db.models import (
    Booking,
    Channel,
    Client,
    Conversation,
    ConversationState,
    Message,
    MessageRole,
    SalonSetting,
)
from app.notify import Notifier
from app.scheduler import Jobs

T = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)  # запис: пт 06.11 14:00 Київ


class Out:
    def __init__(self, ok=True):
        self.admin: list[str] = []
        self.tg: list[tuple[str, str]] = []
        self.ig: list[tuple[str, str]] = []
        self.ok = ok

    def notifier(self):
        async def admin(t, kb=None):  # noqa: ANN001
            self.admin.append(t)

        async def tg(rid, t):  # noqa: ANN001
            self.tg.append((rid, t))
            return self.ok

        async def ig(rid, t):  # noqa: ANN001
            self.ig.append((rid, t))
            return self.ok

        return Notifier(admin_sender=admin, senders={Channel.telegram: tg, Channel.instagram: ig})


@pytest.fixture
def settings():
    return Settings(_env_file=None)


def add_booking(engine, salon, *, client="c1", start=T, created=T - timedelta(days=3)):
    with Session(engine) as s, s.begin():
        b = Booking(client_id=salon[client].id, master_id=salon["master"].id,
                    service_id=salon["cut"].id, start_at=start, end_at=start + timedelta(hours=1),
                    source=Channel.telegram, created_at=created)  # fmt: skip
        s.add(b)
        s.flush()
        return b.id


def set_client(engine, salon, **kw):
    with Session(engine) as s, s.begin():
        c = s.get(Client, salon["c1"].id)
        for k, v in kw.items():
            setattr(c, k, v)


async def run(engine, settings, out, now):
    return await rm.send_due_reminders(engine, settings, out.notifier(), now)


async def test_24h_and_2h_reminders_via_telegram(engine, salon, settings):
    set_client(engine, salon, tg_user_id=555)
    with Session(engine) as s, s.begin():
        s.add(SalonSetting(key="address", value="вул. Прикладна, 1"))
    bid = add_booking(engine, salon)
    out = Out()

    assert await run(engine, settings, out, T - timedelta(hours=25)) == []
    sent = await run(engine, settings, out, T - timedelta(hours=23, minutes=59))
    assert sent == [rm.Due(bid, "24h")]
    assert out.tg[0] == (
        "555",
        "Нагадуємо: завтра о 14:00 стрижка у Маргарити. Чекаємо! Якщо плани змінились — "
        "напишіть сюди.",
    )
    assert await run(engine, settings, out, T - timedelta(hours=23)) == []  # без дублів
    sent = await run(engine, settings, out, T - timedelta(hours=1, minutes=59))
    assert sent == [rm.Due(bid, "2h")]
    assert out.tg[1][1] == "Через 2 години, о 14:00, чекаємо вас у M&D, адреса: вул. Прикладна, 1."
    assert await run(engine, settings, out, T - timedelta(minutes=30)) == []
    assert out.admin == []
    with Session(engine) as s:  # нагадування видно в історії діалогу для агента
        texts = [m.text for m in s.scalars(select(Message))]
        assert any(t.startswith("Нагадуємо") for t in texts)


async def test_kyiv_time_in_text_across_dst(engine, salon, settings):
    set_client(engine, salon, tg_user_id=555)
    start = datetime(2026, 7, 10, 11, 0, tzinfo=UTC)  # літній час: 14:00 EEST
    add_booking(engine, salon, start=start, created=start - timedelta(days=5))
    out = Out()
    await run(engine, settings, out, start - timedelta(hours=20))
    assert "о 14:00" in out.tg[0][1]


async def test_no_channel_falls_back_to_admin_with_phone(engine, salon, settings):
    set_client(engine, salon, phone="+380671234567")
    bid = add_booking(engine, salon)
    out = Out()
    assert await run(engine, settings, out, T - timedelta(hours=20)) == []
    assert out.admin == [
        f"📞 Не можу нагадати Олена про запис #{bid} (завтра) — подзвоніть: +380671234567"
    ]


async def test_instagram_only_inside_24h_window(engine, salon, settings):
    set_client(engine, salon, ig_user_id="igsid-1")
    with Session(engine) as s, s.begin():
        s.add(Conversation(client_id=salon["c1"].id, channel=Channel.instagram,
                           last_inbound_at=T - timedelta(hours=30)))  # fmt: skip
    add_booking(engine, salon)
    out = Out()
    # За 20 год до запису клієнт писав 10 год тому → вікно відкрите, нагадуємо в Direct.
    await run(engine, settings, out, T - timedelta(hours=20))
    assert out.ig and not out.admin
    # За 1 год до запису останнє повідомлення було 29 год тому → вікно закрите → адмінам.
    await run(engine, settings, out, T - timedelta(hours=1))
    assert len(out.ig) == 1
    assert out.admin and "через 2 год" in out.admin[0]


async def test_send_failure_goes_to_admin(engine, salon, settings):
    set_client(engine, salon, tg_user_id=555)
    add_booking(engine, salon)
    out = Out(ok=False)
    await run(engine, settings, out, T - timedelta(hours=20))
    assert out.tg and out.admin


async def test_booked_inside_window_not_reminded(engine, salon, settings):
    set_client(engine, salon, tg_user_id=555)
    add_booking(engine, salon, created=T - timedelta(hours=5))  # записалась за 5 год
    out = Out()
    await run(engine, settings, out, T - timedelta(hours=4))
    assert out.tg == []  # 24h пропущено (запис усередині вікна)
    await run(engine, settings, out, T - timedelta(hours=2))
    assert len(out.tg) == 1  # 2h — так


async def test_late_start_only_sends_2h(engine, salon, settings):
    """Сервер лежав до T-1h: 24h не надсилаємо запізно, лише 2h."""
    set_client(engine, salon, tg_user_id=555)
    add_booking(engine, salon)
    out = Out()
    await run(engine, settings, out, T - timedelta(hours=1))
    assert len(out.tg) == 1 and out.tg[0][1].startswith("Через 2 години")
    with Session(engine) as s:
        b = s.scalar(select(Booking))
        assert b.reminded_24h and b.reminded_2h


async def test_cancelled_not_reminded(engine, salon, settings):
    set_client(engine, salon, tg_user_id=555)
    bid = add_booking(engine, salon)
    with Session(engine) as s, s.begin():
        s.get(Booking, bid).status = "cancelled"
    out = Out()
    await run(engine, settings, out, T - timedelta(hours=20))
    assert out.tg == [] and out.admin == []


def test_master_name_genitive():
    assert rm.master_name_gen("Маргарита") == "Маргарити"
    assert rm.master_name_gen("Марія") == "Марії"
    assert rm.master_name_gen("Андрій") == "майстра Андрій"


async def test_auto_resume_job_notifies_admin(engine, salon, settings):
    from app import clients as cl

    with Session(engine) as s, s.begin():
        conv = cl.get_conversation(s, salon["c1"].id, Channel.telegram)
        cl.add_message(s, conv, MessageRole.client, "скарга", now=T - timedelta(hours=13))
        cl.pause(s, conv, now=T - timedelta(hours=13))
        cid = conv.id
    out = Out()
    await Jobs(engine, settings, out.notifier(), clock=lambda: T).auto_resume()
    with Session(engine) as s:
        assert s.get(Conversation, cid).state == ConversationState.ai
    assert out.admin and f"#{cid}" in out.admin[0]


def test_cleanup_old_messages(engine, salon):
    from app import clients as cl

    with Session(engine) as s, s.begin():
        conv = cl.get_conversation(s, salon["c1"].id, Channel.telegram)
        cl.add_message(s, conv, MessageRole.client, "старе", now=T - timedelta(days=400))
        cl.add_message(s, conv, MessageRole.client, "нове", now=T - timedelta(days=10))
    assert rm.cleanup_old_messages(engine, T) == 1
    with Session(engine) as s:
        assert [m.text for m in s.scalars(select(Message))] == ["нове"]
