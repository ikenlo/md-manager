"""Нагадування за 24 і 2 год (docs/SPEC.md, «Логіка запису»).

Канал: Telegram завжди; Instagram — лише якщо клієнт писав за останні 24 год.
Немає каналу → повідомлення в адмін-групу «подзвоніть».
Прапорці reminded_* ставляться ДО відправки (не більше одного нагадування), а невдала
відправка теж іде адмінам — клієнт не залишиться без попередження непомітно.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session, joinedload

from app import clients as cl
from app.config import Settings
from app.db.models import Booking, BookingStatus, Message, MessageRole, SalonSetting
from app.notify import Notifier
from app.text import fmt_time, relative_day

log = logging.getLogger(__name__)

H24 = timedelta(hours=24)
H2 = timedelta(hours=2)


@dataclass(frozen=True)
class Due:
    booking_id: int
    kind: str  # "24h" | "2h"


def _due_kind(b: Booking, now: datetime) -> str | None:
    """Яке нагадування треба зараз, або None. Пропущені/непотрібні позначаються в mark_skipped."""
    if now >= b.start_at:
        return None
    left = b.start_at - now
    if not b.reminded_2h and left <= H2:
        return "2h"
    if not b.reminded_24h and H2 < left <= H24:
        return "24h"
    return None


def _skip_reason(b: Booking, kind: str) -> bool:
    """Записалися вже всередині вікна — щойно отримали підтвердження, нагадувати не треба."""
    window = H24 if kind == "24h" else H2
    return b.created_at > b.start_at - window


def master_name_gen(name: str) -> str:
    """Для «у …»: Маргарита → Маргарити, Марія → Марії; інакше «майстра Ім'я»."""
    if name.endswith("а"):
        return name[:-1] + "и"
    if name.endswith("я"):
        return name[:-1] + "ї"
    return f"майстра {name}"


def reminder_text(b: Booking, kind: str, now: datetime, settings: Settings, address: str) -> str:
    local_day = b.start_at.astimezone(settings.zone).date()
    today = now.astimezone(settings.zone).date()
    when = f"{relative_day(local_day, today)} о {fmt_time(b.start_at, settings.zone)}"
    if kind == "24h":
        return (
            f"Нагадуємо: {when} {b.service.name.lower()} у {master_name_gen(b.master.name)}. "
            "Чекаємо! Якщо плани змінились — напишіть сюди."
        )
    addr = f", адреса: {address}" if address else ""
    return f"Через 2 години, о {fmt_time(b.start_at, settings.zone)}, чекаємо вас у M&D{addr}."


async def send_due_reminders(
    engine: Engine, settings: Settings, notifier: Notifier, now: datetime
) -> list[Due]:
    with Session(engine) as s, s.begin():
        candidates = list(
            s.scalars(
                select(Booking)
                .options(
                    joinedload(Booking.client),
                    joinedload(Booking.service),
                    joinedload(Booking.master),
                )
                .where(
                    Booking.status == BookingStatus.confirmed,
                    Booking.start_at > now,
                    Booking.start_at <= now + H24,
                    (Booking.reminded_24h.is_(False)) | (Booking.reminded_2h.is_(False)),
                )
            )
        )
        address_row = s.get(SalonSetting, "address")
        address = address_row.value if address_row else ""
        jobs: list[tuple[Due, str, tuple | None, str, str | None, int]] = []
        for b in candidates:
            kind = _due_kind(b, now)
            if kind is None:
                continue
            if kind == "2h":
                b.reminded_24h = b.reminded_2h = True
            else:
                b.reminded_24h = True
            if _skip_reason(b, kind):
                continue
            text = reminder_text(b, kind, now, settings, address)
            target = notifier.client_channel(s, b.client, now)
            jobs.append(
                (
                    Due(b.id, kind),
                    text,
                    target,
                    b.client.name or "клієнту",
                    b.client.phone,
                    b.client_id,
                )
            )

    sent: list[Due] = []
    for due, text, target, name, phone, client_id in jobs:
        ok = False
        if target is not None:
            ok = await notifier.send_to_channel(target[0], target[1], text)
        if ok:
            with Session(engine) as s, s.begin():
                conv = cl.get_conversation(s, client_id, target[0])
                cl.add_message(s, conv, MessageRole.assistant, text, now=now)
            sent.append(due)
            continue
        when = "завтра" if due.kind == "24h" else "через 2 год"
        await notifier.admin(
            f"📞 Не можу нагадати {name} про запис #{due.booking_id} ({when}) — "
            f"подзвоніть: {phone or 'телефону немає'}"
        )
    return sent


def cleanup_old_messages(engine: Engine, now: datetime, months: int = 12) -> int:
    cutoff = now - timedelta(days=30 * months)
    with Session(engine) as s, s.begin():
        result = s.execute(delete(Message).where(Message.created_at < cutoff))
        return result.rowcount or 0
