"""Операції із записами поверх БД. Слоти рахує лише app/booking/slots.py."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.booking import slots as sl
from app.db.models import (
    Booking,
    BookingStatus,
    Channel,
    Master,
    MasterService,
    ScheduleException,
    Service,
    WorkSchedule,
)
from app.db.session import write_transaction


class BookingError(Exception):
    """Помилка, яку можна показати агенту/адміну."""


class SlotTakenError(BookingError):
    def __init__(self) -> None:
        super().__init__("Слот зайнятий або недоступний")


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise BookingError("Потрібен час із часовою зоною")
    return dt.astimezone(UTC)


def _get_service(session: Session, service_id: int) -> Service:
    service = session.get(Service, service_id)
    if service is None or not service.is_active:
        raise BookingError("Послугу не знайдено")
    return service


def _master_ids_for_service(session: Session, service_id: int, master_id: int | None) -> list[int]:
    q = (
        select(Master.id)
        .join(MasterService, MasterService.master_id == Master.id)
        .where(MasterService.service_id == service_id, Master.is_active.is_(True))
        .order_by(Master.id)
    )
    if master_id is not None:
        q = q.where(Master.id == master_id)
    return list(session.scalars(q))


def load_availability(
    session: Session,
    master_ids: list[int],
    window_from: datetime,
    window_to: datetime,
    *,
    exclude_booking_id: int | None = None,
) -> list[sl.MasterAvailability]:
    """Графік, винятки й зайняті інтервали майстрів у вікні (UTC)."""
    if not master_ids:
        return []
    schedules: dict[int, list[sl.ShiftTemplate]] = {m: [] for m in master_ids}
    for ws in session.scalars(select(WorkSchedule).where(WorkSchedule.master_id.in_(master_ids))):
        schedules[ws.master_id].append(sl.ShiftTemplate(ws.weekday, ws.start_time, ws.end_time))

    exceptions: dict[int, list[sl.DayException]] = {m: [] for m in master_ids}
    day_lo = (window_from - timedelta(days=1)).date()
    day_hi = (window_to + timedelta(days=1)).date()
    for ex in session.scalars(
        select(ScheduleException).where(
            ScheduleException.master_id.in_(master_ids),
            ScheduleException.date.between(day_lo, day_hi),
        )
    ):
        exceptions[ex.master_id].append(
            sl.DayException(ex.date, ex.is_day_off, ex.start_time, ex.end_time)
        )

    busy: dict[int, list[sl.BusyInterval]] = {m: [] for m in master_ids}
    # Запас у добу назад: запис, що почався вчора, може тягнутись на сьогодні.
    q = (
        select(Booking.master_id, Booking.start_at, Booking.end_at, Service.buffer_min)
        .join(Service, Service.id == Booking.service_id)
        .where(
            Booking.master_id.in_(master_ids),
            Booking.status == BookingStatus.confirmed,
            Booking.start_at < window_to,
            Booking.end_at > window_from - timedelta(days=1),
        )
    )
    if exclude_booking_id is not None:
        q = q.where(Booking.id != exclude_booking_id)
    for mid, start_at, end_at, buffer_min in session.execute(q):
        busy[mid].append(sl.BusyInterval(start_at, end_at, buffer_min or 0))

    return [sl.MasterAvailability(m, schedules[m], exceptions[m], busy[m]) for m in master_ids]


def find_free_slots(
    session: Session,
    service_id: int,
    date_from: date,
    date_to: date,
    *,
    master_id: int | None = None,
    now: datetime | None = None,
    tz: ZoneInfo = sl.KYIV,
    min_lead_min: int = 60,
    step_min: int = 15,
    max_slots: int = 6,
) -> list[sl.Slot]:
    now = now or datetime.now(UTC)
    service = _get_service(session, service_id)
    master_ids = _master_ids_for_service(session, service_id, master_id)
    window_from = datetime.combine(date_from, datetime.min.time(), tzinfo=tz).astimezone(UTC)
    window_to = datetime.combine(
        date_to + timedelta(days=2), datetime.min.time(), tzinfo=tz
    ).astimezone(UTC)
    masters = load_availability(session, master_ids, window_from, window_to)
    return sl.find_free_slots(
        masters,
        sl.ServiceSpec(service.duration_min, service.buffer_min),
        date_from,
        date_to,
        now,
        min_lead_min=min_lead_min,
        step_min=step_min,
        max_slots=max_slots,
        tz=tz,
    )


def _check_slot(
    session: Session,
    service: Service,
    master_id: int,
    start_at: datetime,
    now: datetime,
    *,
    tz: ZoneInfo,
    min_lead_min: int,
    exclude_booking_id: int | None = None,
) -> None:
    if master_id not in _master_ids_for_service(session, service.id, master_id):
        raise BookingError("Цей майстер не виконує цю послугу")
    window_from = start_at - timedelta(days=1)
    window_to = start_at + timedelta(days=1)
    (master,) = load_availability(
        session, [master_id], window_from, window_to, exclude_booking_id=exclude_booking_id
    )
    spec = sl.ServiceSpec(service.duration_min, service.buffer_min)
    if not sl.is_slot_free(master, spec, start_at, now, min_lead_min=min_lead_min, tz=tz):
        raise SlotTakenError()


def create_booking(
    *,
    service_id: int,
    master_id: int,
    start_at: datetime,
    client_id: int,
    source: Channel,
    created_by: str = "",
    now: datetime | None = None,
    engine: Engine | None = None,
    tz: ZoneInfo = sl.KYIV,
    min_lead_min: int = 60,
) -> Booking:
    """Створити запис. Перевірка слоту й INSERT — в одній транзакції з блокуванням."""
    start_at = _utc(start_at)
    now = now or datetime.now(UTC)
    with write_transaction(engine) as session:
        service = _get_service(session, service_id)
        _check_slot(session, service, master_id, start_at, now, tz=tz, min_lead_min=min_lead_min)
        booking = Booking(
            client_id=client_id,
            master_id=master_id,
            service_id=service_id,
            start_at=start_at,
            end_at=start_at + timedelta(minutes=service.duration_min),
            status=BookingStatus.confirmed,
            source=source,
            created_by=created_by,
        )
        session.add(booking)
        session.flush()
    # TODO(етап 3): сповіщення в адмін-групу «Новий запис: …»
    return booking


def reschedule_booking(
    booking_id: int,
    new_start_at: datetime,
    *,
    now: datetime | None = None,
    engine: Engine | None = None,
    tz: ZoneInfo = sl.KYIV,
    min_lead_min: int = 60,
) -> Booking:
    new_start_at = _utc(new_start_at)
    now = now or datetime.now(UTC)
    with write_transaction(engine) as session:
        booking = session.get(Booking, booking_id)
        if booking is None or booking.status != BookingStatus.confirmed:
            raise BookingError("Активний запис не знайдено")
        service = _get_service(session, booking.service_id)
        _check_slot(
            session,
            service,
            booking.master_id,
            new_start_at,
            now,
            tz=tz,
            min_lead_min=min_lead_min,
            exclude_booking_id=booking.id,
        )
        booking.start_at = new_start_at
        booking.end_at = new_start_at + timedelta(minutes=service.duration_min)
        booking.reminded_24h = False
        booking.reminded_2h = False
    return booking


def set_status(booking_id: int, status: BookingStatus, *, engine: Engine | None = None) -> Booking:
    """Скасування, неявка, виконано."""
    with write_transaction(engine) as session:
        booking = session.get(Booking, booking_id)
        if booking is None:
            raise BookingError("Запис не знайдено")
        if booking.status != BookingStatus.confirmed:
            raise BookingError(f"Запис уже має статус {booking.status.value}")
        booking.status = status
    return booking
