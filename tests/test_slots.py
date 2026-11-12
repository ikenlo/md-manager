"""Алгоритм слотів (чиста функція). Час у тестах — київський, перевірки — по UTC."""

from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.booking.slots import (
    KYIV,
    BusyInterval,
    DayException,
    MasterAvailability,
    ServiceSpec,
    ShiftTemplate,
    SlotError,
    find_free_slots,
    free_starts,
    is_slot_free,
    shifts_for_day,
)

# 2026-11-09 — понеділок
MON = date(2026, 11, 9)
TUE = MON + timedelta(days=1)
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=KYIV)  # далеко в минулому відносно MON


def kyiv(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=KYIV).astimezone(UTC)


def hhmm(dts):
    return [dt.astimezone(KYIV).strftime("%H:%M") for dt in dts]


def week(start="09:00", end="18:00", days=range(7)):
    return [ShiftTemplate(d, time.fromisoformat(start), time.fromisoformat(end)) for d in days]


def master(mid=1, schedule=None, exceptions=(), busy=()):
    return MasterAvailability(mid, schedule if schedule is not None else week(), exceptions, busy)


# --- базова сітка ---------------------------------------------------------


def test_step_15_and_last_slot_fits_shift_end():
    m = master(schedule=week("09:00", "11:00"))
    starts = free_starts(m, ServiceSpec(60, 0), MON, kyiv(MON, 0))
    assert hhmm(starts) == ["09:00", "09:15", "09:30", "09:45", "10:00"]


def test_buffer_of_new_service_must_fit_before_shift_end():
    m = master(schedule=week("09:00", "11:00"))
    starts = free_starts(m, ServiceSpec(60, 15), MON, kyiv(MON, 0))
    assert hhmm(starts)[-1] == "09:45"


def test_service_longer_than_shift_has_no_slots():
    m = master(schedule=week("09:00", "10:00"))
    assert free_starts(m, ServiceSpec(90, 0), MON, kyiv(MON, 0)) == []


def test_existing_booking_blocks_its_time():
    busy = [BusyInterval(kyiv(MON, 10), kyiv(MON, 11), 0)]
    m = master(schedule=week("09:00", "12:00"), busy=busy)
    starts = hhmm(free_starts(m, ServiceSpec(60, 0), MON, kyiv(MON, 0)))
    assert starts == ["09:00", "11:00"]


def test_slot_exactly_adjacent_to_booking_is_valid():
    """Новий запис 09:00–10:00 закінчується рівно тоді, коли починається наступний."""
    busy = [BusyInterval(kyiv(MON, 10), kyiv(MON, 11), 0)]
    m = master(schedule=week("09:00", "12:00"), busy=busy)
    assert is_slot_free(m, ServiceSpec(60, 0), kyiv(MON, 9), NOW)
    assert not is_slot_free(m, ServiceSpec(60, 0), kyiv(MON, 9, 15), NOW)


def test_existing_booking_buffer_blocks_after_it():
    busy = [BusyInterval(kyiv(MON, 10), kyiv(MON, 11), 15)]
    m = master(schedule=week("09:00", "13:00"), busy=busy)
    starts = hhmm(free_starts(m, ServiceSpec(60, 0), MON, kyiv(MON, 0)))
    assert "11:00" not in starts
    assert "11:15" in starts


def test_new_service_buffer_must_fit_before_next_booking():
    busy = [BusyInterval(kyiv(MON, 10), kyiv(MON, 11), 0)]
    m = master(schedule=week("09:00", "12:00"), busy=busy)
    # 60 хв + 15 буфер: 09:00 вже не влазить до 10:00
    assert not is_slot_free(m, ServiceSpec(60, 15), kyiv(MON, 9), NOW)
    assert is_slot_free(m, ServiceSpec(45, 15), kyiv(MON, 9), NOW)


def test_gap_between_bookings_too_small():
    busy = [
        BusyInterval(kyiv(MON, 9), kyiv(MON, 10), 0),
        BusyInterval(kyiv(MON, 10, 45), kyiv(MON, 12), 0),
    ]
    m = master(schedule=week("09:00", "12:00"), busy=busy)
    assert free_starts(m, ServiceSpec(60, 0), MON, kyiv(MON, 0)) == []


# --- винятки графіка --------------------------------------------------------


def test_regular_day_off_by_weekday():
    m = master(schedule=week(days=[1, 2, 3, 4, 5]))  # пн вихідний
    assert free_starts(m, ServiceSpec(60, 0), MON, kyiv(MON, 0)) == []
    assert free_starts(m, ServiceSpec(60, 0), TUE, kyiv(MON, 0))


def test_exception_day_off():
    m = master(exceptions=[DayException(MON, is_day_off=True)])
    assert free_starts(m, ServiceSpec(60, 0), MON, kyiv(MON, 0)) == []
    assert free_starts(m, ServiceSpec(60, 0), TUE, kyiv(MON, 0))


def test_exception_changes_hours():
    m = master(exceptions=[DayException(MON, start=time(14), end=time(16))])
    assert hhmm(free_starts(m, ServiceSpec(60, 0), MON, kyiv(MON, 0))) == [
        "14:00",
        "14:15",
        "14:30",
        "14:45",
        "15:00",
    ]


def test_exception_makes_regular_day_off_a_working_day():
    m = master(
        schedule=week(days=[1]),
        exceptions=[DayException(MON, start=time(10), end=time(11))],
    )
    assert hhmm(free_starts(m, ServiceSpec(60, 0), MON, kyiv(MON, 0))) == ["10:00"]


def test_split_shift_with_lunch_break():
    sched = [ShiftTemplate(0, time(9), time(11)), ShiftTemplate(0, time(12), time(14))]
    m = master(schedule=sched)
    starts = hhmm(free_starts(m, ServiceSpec(90, 0), MON, kyiv(MON, 0)))
    assert starts == ["09:00", "09:15", "09:30", "12:00", "12:15", "12:30"]


# --- «зараз» і lead time --------------------------------------------------


def test_slots_before_now_plus_lead_are_dropped():
    m = master(schedule=week("09:00", "18:00"))
    now = datetime.combine(MON, time(10, 5), tzinfo=KYIV)
    slots = find_free_slots([m], ServiceSpec(60, 0), MON, MON, now, max_slots=50)
    assert hhmm(s.start_at for s in slots)[0] == "11:15"


def test_lead_time_is_configurable():
    m = master(schedule=week("09:00", "18:00"))
    now = datetime.combine(MON, time(10, 0), tzinfo=KYIV)
    slots = find_free_slots([m], ServiceSpec(60, 0), MON, MON, now, min_lead_min=0, max_slots=50)
    assert hhmm(s.start_at for s in slots)[0] == "10:00"


def test_is_slot_free_rejects_past_and_outside_shift():
    m = master(schedule=week("09:00", "18:00"))
    now = datetime.combine(MON, time(12), tzinfo=KYIV)
    assert not is_slot_free(m, ServiceSpec(60, 0), kyiv(MON, 11), now)  # минуле
    assert not is_slot_free(m, ServiceSpec(60, 0), kyiv(MON, 12, 30), now)  # < lead
    assert not is_slot_free(m, ServiceSpec(60, 0), kyiv(MON, 17, 30), now)  # за зміною
    assert is_slot_free(m, ServiceSpec(60, 0), kyiv(MON, 17), now)


def test_naive_datetime_rejected():
    m = master()
    with pytest.raises(SlotError):
        find_free_slots([m], ServiceSpec(60, 0), MON, MON, datetime(2026, 11, 9, 9))


# --- перехід на літній / зимовий час (Київ) ---------------------------------
# 2026-03-29: 03:00 → 04:00 (UTC+2 → UTC+3); 2026-10-25: 04:00 → 03:00 (UTC+3 → UTC+2)

SPRING = date(2026, 3, 29)
AUTUMN = date(2026, 10, 25)


def test_dst_spring_forward_daytime_shift_maps_to_correct_utc():
    m = master(schedule=week("09:00", "18:00"))
    before = free_starts(
        m, ServiceSpec(60, 0), SPRING - timedelta(days=1), kyiv(SPRING, 0) - timedelta(days=2)
    )
    after = free_starts(m, ServiceSpec(60, 0), SPRING, kyiv(SPRING, 0) - timedelta(days=2))
    assert before[0] == datetime(2026, 3, 28, 7, 0, tzinfo=UTC)  # 09:00 EET
    assert after[0] == datetime(2026, 3, 29, 6, 0, tzinfo=UTC)  # 09:00 EEST
    assert hhmm(after)[0] == "09:00" and hhmm(after)[-1] == "17:00"


def test_dst_autumn_back_daytime_shift_maps_to_correct_utc():
    m = master(schedule=week("09:00", "18:00"))
    starts = free_starts(m, ServiceSpec(60, 0), AUTUMN, kyiv(AUTUMN, 0) - timedelta(days=1))
    assert starts[0] == datetime(2026, 10, 25, 7, 0, tzinfo=UTC)  # 09:00 EET
    assert hhmm(starts)[-1] == "17:00"
    assert len(starts) == 33  # 9 год зміни, 60 хв послуга, крок 15


def test_dst_spring_shift_across_gap_is_one_hour_shorter():
    m = master(schedule=week("01:00", "06:00"))
    (shift,) = shifts_for_day(SPRING, m.schedule, {})
    assert shift[1] - shift[0] == timedelta(hours=4)


def test_dst_autumn_shift_across_overlap_is_one_hour_longer():
    m = master(schedule=week("01:00", "06:00"))
    (shift,) = shifts_for_day(AUTUMN, m.schedule, {})
    assert shift[1] - shift[0] == timedelta(hours=6)


def test_dst_nonexistent_local_start_time_moves_forward():
    # 03:30 у ніч на 29.03 не існує (годинник стрибає 03:00 → 04:00).
    # Початок зсувається вперед на 04:30 EEST = 01:30 UTC; зміна не губиться.
    m = master(schedule=week("03:30", "06:00"))
    (shift,) = shifts_for_day(SPRING, m.schedule, {})
    assert shift[0] == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    assert shift[1] == datetime(2026, 3, 29, 3, 0, tzinfo=UTC)  # 06:00 EEST


# --- розподіл результату ----------------------------------------------------


def test_max_six_slots_spread_across_days():
    m = master(schedule=week("09:00", "18:00"))
    slots = find_free_slots([m], ServiceSpec(60, 0), MON, MON + timedelta(days=2), NOW)
    assert len(slots) == 6
    days = [s.local_start().date() for s in slots]
    assert sorted(set(days)) == [MON, TUE, MON + timedelta(days=2)]
    assert all(days.count(d) == 2 for d in set(days))
    assert slots == sorted(slots, key=lambda s: s.start_at)


def test_within_one_day_slots_are_spread_not_consecutive():
    m = master(schedule=week("09:00", "18:00"))
    slots = find_free_slots([m], ServiceSpec(60, 0), MON, MON, NOW)
    assert hhmm(s.start_at for s in slots) == ["09:00", "10:00", "11:00", "13:00", "15:00", "17:00"]


def test_two_masters_same_time_merge_into_one_slot():
    m1 = master(1, schedule=week("09:00", "10:00"))
    m2 = master(2, schedule=week("09:00", "10:00"))
    (slot,) = find_free_slots([m1, m2], ServiceSpec(60, 0), MON, MON, NOW)
    assert slot.master_ids == (1, 2)
    assert slot.end_at - slot.start_at == timedelta(minutes=60)


def test_end_at_excludes_buffer():
    m = master(schedule=week("09:00", "11:00"))
    slot = find_free_slots([m], ServiceSpec(60, 15), MON, MON, NOW)[0]
    assert slot.end_at - slot.start_at == timedelta(minutes=60)


def test_no_masters_or_all_days_off_returns_empty():
    assert find_free_slots([], ServiceSpec(60, 0), MON, TUE, NOW) == []
    m = master(exceptions=[DayException(MON, True), DayException(TUE, True)])
    assert find_free_slots([m], ServiceSpec(60, 0), MON, TUE, NOW) == []


def test_invalid_ranges():
    m = master()
    with pytest.raises(SlotError):
        find_free_slots([m], ServiceSpec(60, 0), TUE, MON, NOW)
    with pytest.raises(SlotError):
        find_free_slots([m], ServiceSpec(60, 0), MON, MON + timedelta(days=40), NOW)
