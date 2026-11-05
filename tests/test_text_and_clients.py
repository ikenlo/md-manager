from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clients as cl
from app.admin.queries import parse_price
from app.db.models import Channel, Client, ConversationState, MessageRole
from app.text import ParseError, fmt_slot, normalize_phone, parse_date, parse_time

TODAY = date(2026, 11, 5)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("20.11", date(2026, 11, 20)),
        ("01.01", date(2027, 1, 1)),  # минула дата без року → наступний рік
        ("05.11", TODAY),
        ("2026-12-01", date(2026, 12, 1)),
        ("20.11.27", date(2027, 11, 20)),
        ("завтра", date(2026, 11, 6)),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw, TODAY) == expected


@pytest.mark.parametrize("raw", ["32.01", "abc", "2026-13-01", ""])
def test_parse_date_errors(raw):
    with pytest.raises(ParseError):
        parse_date(raw, TODAY)


def test_parse_time():
    assert parse_time("9:30") == time(9, 30)
    assert parse_time("14.00") == time(14)
    with pytest.raises(ParseError):
        parse_time("25:00")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("067 123 45 67", "+380671234567"),
        ("+38 (067) 123-45-67", "+380671234567"),
        ("380671234567", "+380671234567"),
        ("671234567", "+380671234567"),
        ("+48 512 345 678", "+48512345678"),
        ("123", None),
        ("абв", None),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_parse_price():
    assert parse_price("600") == (600, None)
    assert parse_price("600–800") == (600, 800)
    with pytest.raises(ValueError):
        parse_price("800-600")


def test_fmt_slot_in_kyiv():
    assert fmt_slot(datetime(2026, 11, 20, 12, 0, tzinfo=UTC)) == "пт 20.11 14:00"


def test_attach_phone_merges_ig_and_tg_client(engine, salon):
    with Session(engine) as s, s.begin():
        ig = cl.get_or_create_ig_client(s, "ig-1", "Олена")
        cl.add_message(
            s, cl.get_conversation(s, ig.id, Channel.instagram), MessageRole.client, "hi"
        )
        ig.phone = "+380671234567"
        tg = cl.get_or_create_tg_client(s, 555, "Олена")
        merged = cl.attach_phone(s, tg, "+380671234567")
        assert merged.id == ig.id
        assert merged.tg_user_id == 555 and merged.ig_user_id == "ig-1"
    with Session(engine) as s:
        assert len(list(s.scalars(select(Client).where(Client.tg_user_id == 555)))) == 1
        assert s.scalar(select(Client).where(Client.ig_user_id == "ig-1")).tg_user_id == 555


def test_auto_resume_after_silence(engine, salon):
    now = datetime(2026, 11, 5, 12, tzinfo=UTC)
    with Session(engine) as s, s.begin():
        conv = cl.get_conversation(s, salon["c1"].id, Channel.telegram)
        cl.add_message(s, conv, MessageRole.client, "скарга", now=now - timedelta(hours=13))
        cl.pause(s, conv, now=now - timedelta(hours=13))
        conv2 = cl.get_conversation(s, salon["c2"].id, Channel.telegram)
        cl.pause(s, conv2, now=now - timedelta(hours=13))
        cl.add_message(s, conv2, MessageRole.admin, "відповідь", now=now - timedelta(hours=1))
        resumed = cl.auto_resume_stale(s, 12, now=now)
        assert resumed == [conv.id]
        assert conv.state == ConversationState.ai and conv2.state == ConversationState.paused
