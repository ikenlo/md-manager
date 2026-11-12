"""Алгоритм вільних слотів. Чистий код: без БД, без I/O, без «зараз» зсередини.

Єдине місце, де рахуються слоти (див. CLAUDE.md). AI лише просить результат.

Правила (docs/SPEC.md, «Логіка запису»):
1. Робочий інтервал дня майстра = work_schedule з поправкою на schedule_exceptions.
2. Зайнято = confirmed-записи + їхній buffer_min.
3. Крок 15 хв; слот валідний, якщо duration_min + buffer_min нової послуги
   влазить до наступного запису або кінця зміни.
4. Не раніше ніж now + min_lead_min.
5. До max_slots слотів, розподілених по днях.

Графік і винятки — у київському (локальному) часі; записи, now і результат — aware UTC.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")
MAX_RANGE_DAYS = 31


@dataclass(frozen=True)
class ShiftTemplate:
    """Звичайна зміна: weekday 0 = понеділок."""

    weekday: int
    start: time
    end: time


@dataclass(frozen=True)
class DayException:
    """Виняток на дату. is_day_off → вихідний; інакше start/end замінюють графік."""

    day: date
    is_day_off: bool = False
    start: time | None = None
    end: time | None = None


@dataclass(frozen=True)
class BusyInterval:
    """Існуючий confirmed-запис: [start_at, end_at) + buffer_min після нього."""

    start_at: datetime
    end_at: datetime
    buffer_min: int = 0

    @property
    def blocked_until(self) -> datetime:
        return self.end_at + timedelta(minutes=self.buffer_min)


@dataclass(frozen=True)
class MasterAvailability:
    master_id: int
    schedule: Sequence[ShiftTemplate]
    exceptions: Sequence[DayException] = ()
    busy: Sequence[BusyInterval] = ()


@dataclass(frozen=True)
class ServiceSpec:
    duration_min: int
    buffer_min: int = 0

    @property
    def occupies(self) -> timedelta:
        return timedelta(minutes=self.duration_min + self.buffer_min)


@dataclass(frozen=True)
class Slot:
    start_at: datetime  # UTC
    end_at: datetime  # UTC, без буфера — коли клієнт іде
    master_ids: tuple[int, ...] = field(default=())

    def local_start(self, tz: ZoneInfo = KYIV) -> datetime:
        return self.start_at.astimezone(tz)


class SlotError(ValueError):
    pass


def _require_aware(dt: datetime, name: str) -> None:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise SlotError(f"{name}: потрібен aware datetime")


def _local_dt(d: date, t: time, tz: ZoneInfo = KYIV) -> datetime:
    """Київська дата+час → UTC.

    Неіснуючий час (весною 03:00–04:00) зсувається вперед: 03:30 → 04:30 EEST.
    Час, що повторюється (восени 03:00–04:00), береться перший раз (EEST).
    Обидва випадки — поведінка zoneinfo з fold=0.
    """
    return datetime.combine(d, t, tzinfo=tz).astimezone(UTC)


def shifts_for_day(
    day: date,
    schedule: Iterable[ShiftTemplate],
    exceptions: Mapping[date, DayException],
    tz: ZoneInfo = KYIV,
) -> list[tuple[datetime, datetime]]:
    """Робочі інтервали майстра на дату (UTC)."""
    exc = exceptions.get(day)
    if exc is not None:
        if exc.is_day_off:
            return []
        if exc.start is not None and exc.end is not None:
            pairs = [(exc.start, exc.end)]
        else:
            pairs = [(s.start, s.end) for s in schedule if s.weekday == day.weekday()]
    else:
        pairs = [(s.start, s.end) for s in schedule if s.weekday == day.weekday()]

    out = []
    for start, end in sorted(pairs):
        s_utc = _local_dt(day, start, tz)
        # end_time 00:00 означає «до півночі»
        end_day = day + timedelta(days=1) if end == time(0) else day
        e_utc = _local_dt(end_day, end, tz)
        if e_utc > s_utc:
            out.append((s_utc, e_utc))
    return out


def _overlaps(start: datetime, end: datetime, busy: Iterable[BusyInterval]) -> bool:
    return any(start < b.blocked_until and b.start_at < end for b in busy)


def free_starts(
    master: MasterAvailability,
    service: ServiceSpec,
    day: date,
    earliest: datetime,
    *,
    step_min: int = 15,
    tz: ZoneInfo = KYIV,
) -> list[datetime]:
    """Усі валідні початки для майстра в цей день (UTC), відсортовані."""
    exceptions = {e.day: e for e in master.exceptions}
    step = timedelta(minutes=step_min)
    need = service.occupies
    out: list[datetime] = []
    for shift_start, shift_end in shifts_for_day(day, master.schedule, exceptions, tz):
        busy = [b for b in master.busy if b.start_at < shift_end and b.blocked_until > shift_start]
        t = shift_start
        while t + need <= shift_end:
            if t >= earliest and not _overlaps(t, t + need, busy):
                out.append(t)
            t += step
    return out


def is_slot_free(
    master: MasterAvailability,
    service: ServiceSpec,
    start_at: datetime,
    now: datetime,
    *,
    min_lead_min: int = 60,
    tz: ZoneInfo = KYIV,
) -> bool:
    """Повторна перевірка одного слоту (для create_booking / перенесення).

    Не вимагає вирівнювання по сітці 15 хв: адмін може записати на 10:10.
    """
    _require_aware(start_at, "start_at")
    _require_aware(now, "now")
    start_at = start_at.astimezone(UTC)
    if start_at < now.astimezone(UTC) + timedelta(minutes=min_lead_min):
        return False
    end = start_at + service.occupies
    day = start_at.astimezone(tz).date()
    exceptions = {e.day: e for e in master.exceptions}
    in_shift = any(
        s <= start_at and end <= e for s, e in shifts_for_day(day, master.schedule, exceptions, tz)
    )
    return in_shift and not _overlaps(start_at, end, master.busy)


def _spread_order(starts: list[datetime], gap: timedelta) -> list[datetime]:
    """Порядок вибору в межах дня: щоб слоти не йшли підряд.

    Кілька проходів зі зменшенням проміжку (gap, gap/2, gap/4, 0): у кожному
    беремо час, віддалений від усіх уже вибраних щонайменше на поточний проміжок.
    """
    picked: list[datetime] = []
    for g in (gap, gap / 2, gap / 4, timedelta(0)):
        for t in starts:
            if t not in picked and all(abs(t - p) >= g for p in picked):
                picked.append(t)
    return picked


def find_free_slots(
    masters: Sequence[MasterAvailability],
    service: ServiceSpec,
    date_from: date,
    date_to: date,
    now: datetime,
    *,
    min_lead_min: int = 60,
    step_min: int = 15,
    max_slots: int = 6,
    spread_gap_min: int = 120,
    tz: ZoneInfo = KYIV,
) -> list[Slot]:
    """До max_slots найближчих вільних слотів, розподілених по днях.

    Якщо в один час вільні кілька майстрів — це один слот з кількома master_ids.
    Результат відсортований за часом.
    """
    _require_aware(now, "now")
    if date_to < date_from:
        raise SlotError("date_to раніше за date_from")
    if (date_to - date_from).days >= MAX_RANGE_DAYS:
        raise SlotError(f"Діапазон більший за {MAX_RANGE_DAYS} днів")
    if service.duration_min <= 0:
        raise SlotError("Тривалість послуги має бути > 0")

    earliest = now.astimezone(UTC) + timedelta(minutes=min_lead_min)
    duration = timedelta(minutes=service.duration_min)

    per_day: dict[date, dict[datetime, list[int]]] = defaultdict(lambda: defaultdict(list))
    d = date_from
    while d <= date_to:
        for m in masters:
            for t in free_starts(m, service, d, earliest, step_min=step_min, tz=tz):
                per_day[d][t].append(m.master_id)
        d += timedelta(days=1)

    return pick_spread(per_day, duration, max_slots=max_slots, spread_gap_min=spread_gap_min)


def pick_spread(
    per_day: Mapping[date, Mapping[datetime, Sequence[int]]],
    duration: timedelta,
    *,
    max_slots: int = 6,
    spread_gap_min: int = 120,
) -> list[Slot]:
    """До max_slots слотів, розподілених по днях і в межах дня; результат — за часом.

    per_day: день → {початок (UTC) → id майстрів, вільних у цей час}.
    """
    gap = timedelta(minutes=spread_gap_min)
    queues = {
        day: _spread_order(sorted(starts), gap) for day, starts in sorted(per_day.items()) if starts
    }
    chosen: list[tuple[date, datetime]] = []
    while len(chosen) < max_slots and any(queues.values()):
        for day in sorted(queues):
            if queues[day] and len(chosen) < max_slots:
                chosen.append((day, queues[day].pop(0)))

    return [
        Slot(start_at=t, end_at=t + duration, master_ids=tuple(sorted(per_day[day][t])))
        for day, t in sorted(chosen, key=lambda x: x[1])
    ]
