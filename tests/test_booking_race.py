"""create_booking: транзакційна перевірка і одночасний запис двох клієнтів."""

import threading
import time as _time
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.booking import service as bs
from app.booking.slots import KYIV
from app.db.models import Booking, BookingStatus, Channel, ScheduleException

DAY = date(2026, 11, 10)
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def at(hh, mm=0, d=DAY):
    return datetime.combine(d, time(hh, mm), tzinfo=KYIV)


def book(engine, salon, start, client="c1", **kw):
    return bs.create_booking(
        service_id=salon["cut"].id,
        master_id=salon["master"].id,
        start_at=start,
        client_id=salon[client].id,
        source=Channel.telegram,
        now=NOW,
        engine=engine,
        **kw,
    )


def confirmed_count(engine):
    with Session(engine) as s:
        return s.scalar(
            select(func.count())
            .select_from(Booking)
            .where(Booking.status == BookingStatus.confirmed)
        )


def test_create_booking_stores_utc_and_end_without_buffer(engine, salon):
    b = book(engine, salon, at(14))
    with Session(engine) as s:
        row = s.get(Booking, b.id)
        assert row.start_at == datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
        assert row.end_at - row.start_at == timedelta(minutes=60)
        assert row.status == BookingStatus.confirmed


def test_same_slot_twice_is_rejected(engine, salon):
    book(engine, salon, at(14))
    with pytest.raises(bs.SlotTakenError):
        book(engine, salon, at(14), client="c2")


def test_overlap_including_buffer_is_rejected(engine, salon):
    book(engine, salon, at(14))  # 14:00–15:00 + 15 хв буфер
    with pytest.raises(bs.SlotTakenError):
        book(engine, salon, at(15), client="c2")
    book(engine, salon, at(15, 15), client="c2")
    with pytest.raises(bs.SlotTakenError):
        book(engine, salon, at(13, 15), client="c2")  # 13:15+60+15 = 14:30 > 14:00
    book(engine, salon, at(12, 45), client="c2")  # рівно впритул: 12:45+75 = 14:00


def test_master_who_does_not_do_service_is_rejected(engine, salon):
    with pytest.raises(bs.BookingError):
        bs.create_booking(
            service_id=salon["nails"].id,
            master_id=salon["master"].id,
            start_at=at(10),
            client_id=salon["c1"].id,
            source=Channel.admin,
            now=NOW,
            engine=engine,
        )


def test_day_off_exception_blocks_booking_and_slots(engine, salon):
    with Session(engine) as s, s.begin():
        s.add(ScheduleException(master_id=salon["master"].id, date=DAY, is_day_off=True))
    with pytest.raises(bs.SlotTakenError):
        book(engine, salon, at(10))
    with Session(engine) as s:
        assert bs.find_free_slots(s, salon["cut"].id, DAY, DAY, now=NOW) == []


def test_find_free_slots_from_db_skips_booked_time(engine, salon):
    book(engine, salon, at(9))
    with Session(engine) as s:
        slots = bs.find_free_slots(s, salon["cut"].id, DAY, DAY, now=NOW, max_slots=50)
    starts = [sl.local_start().strftime("%H:%M") for sl in slots]
    assert "09:00" not in starts and "10:00" not in starts
    assert starts[0] == "10:15"
    assert all(sl.master_ids == (salon["master"].id,) for sl in slots)


def test_cancel_frees_slot(engine, salon):
    b = book(engine, salon, at(14))
    bs.set_status(b.id, BookingStatus.cancelled, engine=engine)
    book(engine, salon, at(14), client="c2")
    with pytest.raises(bs.BookingError):
        bs.set_status(b.id, BookingStatus.no_show, engine=engine)


def test_reschedule_checks_slot_and_ignores_own_booking(engine, salon):
    a = book(engine, salon, at(10))
    book(engine, salon, at(14), client="c2")
    # зсув на 30 хв перетинається лише із самим собою → дозволено
    moved = bs.reschedule_booking(a.id, at(10, 30), now=NOW, engine=engine)
    assert moved.start_at == at(10, 30).astimezone(UTC)
    assert moved.reminded_24h is False
    with pytest.raises(bs.SlotTakenError):
        bs.reschedule_booking(a.id, at(13, 30), now=NOW, engine=engine)


def test_two_clients_book_same_slot_concurrently(engine, salon, monkeypatch):
    """Обидва потоки одночасно в критичній секції: без блокування обидва побачили б
    «вільно» і створили по запису. Затримка між читанням і INSERT робить гонку
    гарантованою, а не випадковою."""
    real_load = bs.load_availability
    inside = threading.Event()

    def slow_load(*a, **kw):
        result = real_load(*a, **kw)
        inside.set()
        _time.sleep(0.3)
        return result

    monkeypatch.setattr(bs, "load_availability", slow_load)

    barrier = threading.Barrier(2)
    results: list[object] = []

    def worker(client):
        barrier.wait()
        try:
            results.append(book(engine, salon, at(14), client=client))
        except Exception as e:  # noqa: BLE001
            results.append(e)

    threads = [threading.Thread(target=worker, args=(c,)) for c in ("c1", "c2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    ok = [r for r in results if isinstance(r, Booking)]
    errors = [r for r in results if isinstance(r, Exception)]
    assert len(ok) == 1, results
    assert len(errors) == 1 and isinstance(errors[0], bs.SlotTakenError), errors
    assert confirmed_count(engine) == 1


def test_many_concurrent_overlapping_bookings_only_one_wins(engine, salon):
    starts = [at(14), at(14, 15), at(14, 30), at(13, 30)]  # усі перетинаються з 14:00
    barrier = threading.Barrier(len(starts))
    results: list[object] = []

    def worker(start):
        barrier.wait()
        try:
            results.append(book(engine, salon, start))
        except Exception as e:  # noqa: BLE001
            results.append(e)

    threads = [threading.Thread(target=worker, args=(s,)) for s in starts]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sum(isinstance(r, Booking) for r in results) == 1, results
    assert all(isinstance(r, bs.SlotTakenError) for r in results if not isinstance(r, Booking))
