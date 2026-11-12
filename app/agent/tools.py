"""Сім інструментів агента. Агент лише просить — пише в БД цей код."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, joinedload

from app import clients as cl
from app.booking import service as bs
from app.config import Settings
from app.db.models import (
    Booking,
    BookingStatus,
    Channel,
    Client,
    Conversation,
    Master,
    MasterService,
    Service,
)
from app.integrations.mds import MdsError
from app.notify import Notifier
from app.text import fmt_price, fmt_slot, normalize_phone

log = logging.getLogger(__name__)

MAX_SLOT_RANGE_DAYS = 14


TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_services",
        "description": "Послуги салону: id, назва, ціна, тривалість, які майстри роблять.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Фільтр за категорією"},
            },
        },
    },
    {
        "name": "get_masters",
        "description": "Майстри та їхні послуги. Можна відфільтрувати за послугою.",
        "input_schema": {
            "type": "object",
            "properties": {"service_id": {"type": "integer"}},
        },
    },
    {
        "name": "find_free_slots",
        "description": (
            "Повертає вільні слоти для послуги. Викликай ЗАВЖДИ перед тим, як називати "
            "клієнту час. Діапазон — до 14 днів."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service_id": {"type": "integer"},
                "date_from": {"type": "string", "description": "YYYY-MM-DD, Київ"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD, Київ"},
                "master_id": {"type": "integer"},
            },
            "required": ["service_id", "date_from", "date_to"],
        },
    },
    {
        "name": "create_booking",
        "description": (
            "Створює запис. Лише після того, як клієнт явно підтвердив послугу, майстра, "
            "дату і час. start_at — значення start з find_free_slots."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service_id": {"type": "integer"},
                "master_id": {"type": "integer"},
                "start_at": {
                    "type": "string",
                    "description": "ISO 8601, напр. 2026-11-20T14:00+02:00",
                },
                "client_name": {"type": "string"},
                "client_phone": {"type": "string"},
            },
            "required": ["service_id", "master_id", "start_at", "client_name"],
        },
    },
    {
        "name": "get_client_bookings",
        "description": "Майбутні записи цього клієнта.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancel_or_reschedule",
        "description": (
            "Скасовує запис клієнта (без new_start_at) або переносить його на new_start_at. "
            "Перед перенесенням перевір час через find_free_slots."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "integer"},
                "new_start_at": {"type": "string", "description": "ISO 8601"},
            },
            "required": ["booking_id"],
        },
    },
    {
        "name": "handoff_to_human",
        "description": (
            "Передає діалог живому адміністратору: скарги, медичні питання, складні випадки, "
            "прохання покликати людину. Після виклику бот замовкає в цьому діалозі."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Коротко, чому"},
                "summary": {"type": "string", "description": "Підсумок діалогу для адміна"},
            },
            "required": ["reason", "summary"],
        },
    },
]


@dataclass
class ToolContext:
    engine: Engine
    settings: Settings
    notifier: Notifier
    client_id: int
    conversation_id: int
    channel: Channel
    now: datetime
    mds: Any = None  # MdsClient, якщо записи ведуться в MDS Connect
    lead_source: str | None = None  # мітка посилання / реклами, з якої прийшов клієнт
    handed_off: bool = False
    bookings_created: list[int] = field(default_factory=list)


class ToolError(Exception):
    """Помилка, яку бачить модель (is_error=True)."""


def _parse_dt(value: str, settings: Settings) -> datetime:
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as e:
        raise ToolError(f"Некоректний час: {value}. Формат ISO 8601") from e
    if dt.tzinfo is None:  # без зони — київський час
        dt = dt.replace(tzinfo=settings.zone)
    return dt.astimezone(UTC)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError as e:
        raise ToolError(f"Некоректна дата: {value}. Формат YYYY-MM-DD") from e


def _slot_json(start: datetime, settings: Settings) -> dict[str, str]:
    return {"start": start.astimezone(settings.zone).isoformat(timespec="minutes"),
            "label": fmt_slot(start, settings.zone)}  # fmt: skip


def get_services(ctx: ToolContext, category: str | None = None) -> dict[str, Any]:
    with Session(ctx.engine) as s:
        q = select(Service).options(joinedload(Service.masters)).where(Service.is_active.is_(True))
        if category:
            q = q.where(Service.category.ilike(f"%{category}%"))
        services = s.scalars(q.order_by(Service.category, Service.name)).unique()
        return {
            "services": [
                {
                    "id": x.id,
                    "name": x.name,
                    "category": x.category,
                    "price": fmt_price(x.price_from, x.price_to),
                    "duration_min": x.duration_min,
                    "masters": [m.name for m in x.masters if m.is_active],
                }
                for x in services
            ]
        }


def get_masters(ctx: ToolContext, service_id: int | None = None) -> dict[str, Any]:
    with Session(ctx.engine) as s:
        q = select(Master).options(joinedload(Master.services)).where(Master.is_active.is_(True))
        if service_id is not None:
            q = q.join(MasterService, MasterService.master_id == Master.id).where(
                MasterService.service_id == service_id
            )
        masters = s.scalars(q.order_by(Master.id)).unique()
        return {
            "masters": [
                {
                    "id": m.id,
                    "name": m.name,
                    "services": [{"id": x.id, "name": x.name} for x in m.services if x.is_active],
                }
                for m in masters
            ]
        }


def find_free_slots(
    ctx: ToolContext,
    service_id: int,
    date_from: str,
    date_to: str,
    master_id: int | None = None,
) -> dict[str, Any]:
    today = ctx.now.astimezone(ctx.settings.zone).date()
    d_from = max(_parse_date(date_from), today)
    d_to = _parse_date(date_to)
    if d_to < d_from:
        d_to = d_from
    d_to = min(d_to, d_from + timedelta(days=MAX_SLOT_RANGE_DAYS - 1))
    with Session(ctx.engine) as s:
        try:
            slots = bs.find_free_slots(
                s, service_id, d_from, d_to, master_id=master_id, now=ctx.now,
                tz=ctx.settings.zone, min_lead_min=ctx.settings.min_lead_min,
                step_min=ctx.settings.slot_step_min, max_slots=ctx.settings.max_slots,
            )  # fmt: skip
        except bs.BookingError as e:
            raise ToolError(str(e)) from e
        names = dict(s.execute(select(Master.id, Master.name)).all())
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "slots": [
            {
                **_slot_json(x.start_at, ctx.settings),
                "masters": [{"id": m, "name": names[m]} for m in x.master_ids],
            }
            for x in slots
        ],
    }


async def create_booking(
    ctx: ToolContext,
    service_id: int,
    master_id: int,
    start_at: str,
    client_name: str,
    client_phone: str | None = None,
) -> dict[str, Any]:
    start = _parse_dt(start_at, ctx.settings)
    with Session(ctx.engine, expire_on_commit=False) as s, s.begin():
        client = s.get(Client, ctx.client_id)
        if client_name.strip():
            client.name = client_name.strip()[:100]
        if client_phone:
            phone = normalize_phone(client_phone)
            if phone is None:
                raise ToolError("Некоректний телефон. Попроси клієнта перевірити номер")
            client = cl.attach_phone(s, client, phone)
            if client.id != ctx.client_id:  # об'єднали з наявним клієнтом
                conv = s.get(Conversation, ctx.conversation_id)
                ctx.client_id = conv.client_id = client.id
    source = ctx.channel if ctx.channel != Channel.admin else Channel.admin
    try:
        booking = await asyncio.to_thread(
            bs.create_booking,
            service_id=service_id,
            master_id=master_id,
            start_at=start,
            client_id=ctx.client_id,
            source=source,
            created_by="ai",
            now=ctx.now,
            engine=ctx.engine,
            tz=ctx.settings.zone,
            min_lead_min=ctx.settings.min_lead_min,
        )
    except bs.SlotTakenError:
        return {"ok": False, "error": "slot_taken", "message": "Цей час уже зайнятий"}
    except bs.BookingError as e:
        raise ToolError(str(e)) from e
    if ctx.lead_source:
        with Session(ctx.engine) as s, s.begin():
            s.get(Booking, booking.id).lead_source = ctx.lead_source
    ctx.bookings_created.append(booking.id)
    from app.channels.telegram import announce_booking

    summary = await announce_booking(ctx.engine, ctx.notifier, booking.id)
    return {"ok": True, "booking_id": booking.id, "summary": summary}


def _own_upcoming(s: Session, ctx: ToolContext) -> list[Booking]:
    return list(
        s.scalars(
            select(Booking)
            .options(joinedload(Booking.service), joinedload(Booking.master))
            .where(
                Booking.client_id == ctx.client_id,
                Booking.status == BookingStatus.confirmed,
                Booking.start_at >= ctx.now,
            )
            .order_by(Booking.start_at)
        )
    )


def get_client_bookings(ctx: ToolContext) -> dict[str, Any]:
    with Session(ctx.engine) as s:
        return {
            "bookings": [
                {
                    "booking_id": b.id,
                    **_slot_json(b.start_at, ctx.settings),
                    "service": b.service.name,
                    "master": b.master.name,
                }
                for b in _own_upcoming(s, ctx)
            ]
        }


async def cancel_or_reschedule(
    ctx: ToolContext, booking_id: int, new_start_at: str | None = None
) -> dict[str, Any]:
    with Session(ctx.engine) as s:
        if booking_id not in {b.id for b in _own_upcoming(s, ctx)}:
            raise ToolError("Серед майбутніх записів клієнта такого немає")
    from app.admin.queries import booking_summary, load_booking

    try:
        if new_start_at:
            start = _parse_dt(new_start_at, ctx.settings)
            await asyncio.to_thread(
                bs.reschedule_booking, booking_id, start, now=ctx.now, engine=ctx.engine,
                tz=ctx.settings.zone, min_lead_min=ctx.settings.min_lead_min,
            )  # fmt: skip
            action, icon = "перенесено", "🔁"
        else:
            await asyncio.to_thread(
                bs.set_status, booking_id, BookingStatus.cancelled, engine=ctx.engine
            )
            action, icon = "скасовано", "🚫"
    except bs.SlotTakenError:
        return {"ok": False, "error": "slot_taken", "message": "Цей час уже зайнятий"}
    except bs.BookingError as e:
        raise ToolError(str(e)) from e
    with Session(ctx.engine) as s:
        summary = booking_summary(load_booking(s, booking_id))
    await ctx.notifier.admin(f"{icon} AI: запис #{booking_id} {action}: {summary}")
    return {"ok": True, "status": action, "summary": summary}


async def handoff_to_human(ctx: ToolContext, reason: str, summary: str) -> dict[str, Any]:
    await do_handoff(ctx.engine, ctx.notifier, ctx.conversation_id, reason, summary, ctx.now)
    ctx.handed_off = True
    return {
        "ok": True,
        "message": "Адміністратора покликано. Скажи клієнту, що він скоро відповість.",
    }


async def do_handoff(
    engine: Engine,
    notifier: Notifier,
    conversation_id: int,
    reason: str,
    summary: str = "",
    now: datetime | None = None,
) -> None:
    """Пауза діалогу + сповіщення в адмін-групу з кнопками."""
    from app.channels.telegram import conversation_keyboard

    with Session(engine, expire_on_commit=False) as s, s.begin():
        conv = s.get(Conversation, conversation_id)
        cl.pause(s, conv, now)
        client = s.get(Client, conv.client_id)
        name = client.name or "Клієнт"
        channel = conv.channel
        keyboard = conversation_keyboard(conv, client)
    text = (
        f"🙋 Потрібен адміністратор — діалог #{conversation_id} ({channel.value}), {name}\n"
        f"Причина: {reason}"
    )
    if summary:
        text += f"\nПідсумок: {summary}"
    text += (
        f"\nВідповісти: /reply {conversation_id} текст · Повернути AI: /resume {conversation_id}"
    )
    await notifier.admin(text, keyboard)


HANDLERS = {
    "get_services": get_services,
    "get_masters": get_masters,
    "find_free_slots": find_free_slots,
    "create_booking": create_booking,
    "get_client_bookings": get_client_bookings,
    "cancel_or_reschedule": cancel_or_reschedule,
    "handoff_to_human": handoff_to_human,
}


async def execute(ctx: ToolContext, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Виконати інструмент. Повертає (результат, is_error)."""
    if ctx.mds is not None:
        from app.agent import mds_tools

        handler = mds_tools.HANDLERS.get(name)
    else:
        handler = HANDLERS.get(name)
    if handler is None:
        return {"error": f"Невідомий інструмент {name}"}, True
    try:
        result = handler(ctx, **(args or {}))
        if asyncio.iscoroutine(result):
            result = await result
        return result, False
    except ToolError as e:
        return {"error": str(e)}, True
    except MdsError as e:
        log.warning("tool %s: MDS %s %s", name, e.status, e.code)
        return {"error": e.message}, True
    except TypeError as e:  # неправильні аргументи від моделі
        return {"error": f"Неправильні параметри: {e}"}, True
    except Exception:
        log.exception("tool %s failed", name)
        return {"error": "Внутрішня помилка. Запропонуй покликати адміністратора"}, True
