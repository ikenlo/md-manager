"""Логіка адмінки: тексти розкладу, картки клієнта, статистики, вихідні, прайс.

Хендлери в app/admin/commands.py лише розбирають команду і викликають це.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import (
    Booking,
    BookingStatus,
    Channel,
    Client,
    Conversation,
    Master,
    Message,
    MessageRole,
    ScheduleException,
    Service,
)
from app.text import day_bounds_utc, fmt_date_long, fmt_price, fmt_slot, fmt_time

STATUS_MARK = {
    BookingStatus.confirmed: "",
    BookingStatus.completed: " ✅",
    BookingStatus.no_show: " ❌ неявка",
    BookingStatus.cancelled: " 🚫 скасовано",
}
SOURCE_MARK = {Channel.instagram: "IG", Channel.telegram: "TG", Channel.admin: "адм"}


def find_master(session: Session, query: str) -> Master | None:
    """За id або за початком імені (без регістру)."""
    if query.isdigit():
        return session.get(Master, int(query))
    q = query.strip().lower()
    masters = [m for m in session.scalars(select(Master)) if m.name.lower().startswith(q)]
    return masters[0] if len(masters) == 1 else None


def day_schedule(session: Session, d: date) -> str:
    start, end = day_bounds_utc(d)
    bookings = list(
        session.scalars(
            select(Booking)
            .options(
                joinedload(Booking.client), joinedload(Booking.master), joinedload(Booking.service)
            )
            .where(
                Booking.start_at >= start,
                Booking.start_at < end,
                Booking.status != BookingStatus.cancelled,
            )
            .order_by(Booking.master_id, Booking.start_at)
        )
    )
    off = {
        e.master_id
        for e in session.scalars(
            select(ScheduleException).where(
                ScheduleException.date == d, ScheduleException.is_day_off.is_(True)
            )
        )
    }
    lines = [f"📅 {fmt_date_long(d)}"]
    masters = list(session.scalars(select(Master).where(Master.is_active.is_(True))))
    for m in masters:
        mine = [b for b in bookings if b.master_id == m.id]
        lines.append("")
        lines.append(f"👤 {m.name}" + (" — вихідний" if m.id in off else ""))
        if not mine:
            lines.append("  записів немає")
        for b in mine:
            lines.append(
                f"  {fmt_time(b.start_at)}–{fmt_time(b.end_at)} {b.service.name} — "
                f"{b.client.name or 'без імені'} [#{b.id}, {SOURCE_MARK[b.source]}]"
                f"{STATUS_MARK[b.status]}"
            )
    if not masters:
        lines.append("Немає активних майстрів")
    return "\n".join(lines)


def booking_summary(b: Booking) -> str:
    return f"{b.client.name or 'Клієнт'}, {b.service.name}, {fmt_slot(b.start_at)}, {b.master.name}"


def load_booking(session: Session, booking_id: int) -> Booking | None:
    return session.scalar(
        select(Booking)
        .options(
            joinedload(Booking.client), joinedload(Booking.master), joinedload(Booking.service)
        )
        .where(Booking.id == booking_id)
    )


def client_card(session: Session, client: Client, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    bookings = list(
        session.scalars(
            select(Booking)
            .options(joinedload(Booking.service), joinedload(Booking.master))
            .where(Booking.client_id == client.id)
            .order_by(Booking.start_at.desc())
        )
    )
    upcoming = [b for b in bookings if b.status == BookingStatus.confirmed and b.start_at >= now]
    done = sum(b.status == BookingStatus.completed for b in bookings)
    no_show = sum(b.status == BookingStatus.no_show for b in bookings)
    channels = [
        n for n, v in (("Telegram", client.tg_user_id), ("Instagram", client.ig_user_id)) if v
    ]
    lines = [
        f"🗂 {client.name or 'Без імені'} (#{client.id})",
        f"Телефон: {client.phone or '—'}",
        f"Канали: {', '.join(channels) or '—'}",
        f"Візитів: {done}, неявок: {no_show}",
    ]
    if client.notes:
        lines.append(f"Нотатки: {client.notes}")
    if upcoming:
        lines.append("Майбутні записи:")
        for b in sorted(upcoming, key=lambda x: x.start_at):
            lines.append(f"  #{b.id} {fmt_slot(b.start_at)} {b.service.name} — {b.master.name}")
    history = [b for b in bookings if b not in upcoming][:5]
    if history:
        lines.append("Останні:")
        for b in history:
            lines.append(
                f"  #{b.id} {fmt_slot(b.start_at)} {b.service.name}{STATUS_MARK[b.status]}"
            )
    return "\n".join(lines)


def set_day_off(session: Session, master: Master, d: date) -> list[Booking]:
    """Позначити вихідний. Повертає confirmed-записи цього дня, які треба перенести."""
    exc = session.scalar(
        select(ScheduleException).where(
            ScheduleException.master_id == master.id, ScheduleException.date == d
        )
    )
    if exc is None:
        exc = ScheduleException(master_id=master.id, date=d)
        session.add(exc)
    exc.is_day_off = True
    exc.start_time = exc.end_time = None
    start, end = day_bounds_utc(d)
    return list(
        session.scalars(
            select(Booking)
            .options(joinedload(Booking.client), joinedload(Booking.service))
            .where(
                Booking.master_id == master.id,
                Booking.status == BookingStatus.confirmed,
                Booking.start_at >= start,
                Booking.start_at < end,
            )
            .order_by(Booking.start_at)
        )
    )


def price_list(session: Session, *, with_ids: bool = False) -> str:
    services = list(
        session.scalars(
            select(Service)
            .where(Service.is_active.is_(True))
            .order_by(Service.category, Service.name)
        )
    )
    if not services:
        return "Прайс порожній"
    lines, category = [], None
    for s in services:
        if s.category != category:
            category = s.category
            lines.append(f"\n<b>{category or 'Інше'}</b>")
        prefix = f"#{s.id} " if with_ids else ""
        lines.append(
            f"{prefix}{s.name} — {fmt_price(s.price_from, s.price_to)}, {s.duration_min} хв"
        )
    return "\n".join(lines).strip()


def parse_price(text: str) -> tuple[int, int | None]:
    """'600' або '600-800' / '600–800'."""
    parts = text.replace("–", "-").replace(" ", "").split("-")
    try:
        nums = [int(p) for p in parts if p]
    except ValueError as e:
        raise ValueError("Ціна — число або діапазон, напр. 600 або 600-800") from e
    if len(nums) == 1:
        return nums[0], None
    if len(nums) == 2 and nums[0] <= nums[1]:
        return nums[0], nums[1]
    raise ValueError("Ціна — число або діапазон, напр. 600 або 600-800")


def weekly_stats(session: Session, now: datetime | None = None) -> dict[str, float | int]:
    now = now or datetime.now(UTC)
    since = now - timedelta(days=7)
    dialogs = session.scalar(
        select(func.count(func.distinct(Message.conversation_id))).where(
            Message.role == MessageRole.client, Message.created_at >= since
        )
    )
    created = select(func.count()).select_from(Booking).where(Booking.created_at >= since)
    by_bot = session.scalar(created.where(Booking.created_by == "ai"))
    total = session.scalar(created)
    no_shows = session.scalar(
        select(func.count())
        .select_from(Booking)
        .where(
            Booking.status == BookingStatus.no_show,
            Booking.start_at >= since,
            Booking.start_at < now,
        )
    )
    paused = session.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.state == "paused")
    )
    return {
        "dialogs": dialogs or 0,
        "bookings_total": total or 0,
        "bookings_by_ai": by_bot or 0,
        "no_shows": no_shows or 0,
        "paused_dialogs": paused or 0,
    }


def format_stats(stats: dict[str, float | int], ai_cost_usd: float | None = None) -> str:
    lines = [
        "📊 За 7 днів",
        f"Діалогів: {stats['dialogs']}",
        f"Нових записів: {stats['bookings_total']} (від бота: {stats['bookings_by_ai']})",
        f"Неявок: {stats['no_shows']}",
        f"Діалогів на паузі зараз: {stats['paused_dialogs']}",
    ]
    if ai_cost_usd is not None:
        lines.append(f"Витрати на AI: ${ai_cost_usd:.2f}")
    return "\n".join(lines)
