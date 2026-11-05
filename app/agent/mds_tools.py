"""Інструменти агента в режимі MDS Connect: каталог, слоти й записи — через API MDS.

Ті самі назви й формат відповідей, що й у app/agent/tools.py, тож промпт і модель не змінюються.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app import clients as cl
from app.agent.tools import (
    MAX_SLOT_RANGE_DAYS,
    ToolContext,
    ToolError,
    _parse_date,
    _parse_dt,
    _slot_json,
    do_handoff,
    handoff_to_human,
)
from app.booking.slots import pick_spread
from app.db.models import Client, Conversation
from app.integrations.mds import MdsError, channel_for
from app.text import normalize_phone


def _price(kop: int, price_from: bool) -> str:
    uah = kop // 100
    return f"від {uah} грн" if price_from else f"{uah} грн"


async def _catalog(ctx: ToolContext) -> dict[str, Any]:
    return await ctx.mds.catalog()


async def get_services(ctx: ToolContext, category: str | None = None) -> dict[str, Any]:
    cat = await _catalog(ctx)
    names = {m["id"]: m["name"] for m in cat["masters"]}
    out = []
    for x in cat["services"]:
        group = " / ".join(
            p for p in (x.get("section"), x.get("category"), x.get("subcategory")) if p
        )
        if category and category.lower() not in group.lower():
            continue
        out.append(
            {
                "id": x["id"],
                "name": x["name"],
                "category": group,
                "price": _price(x["price"], x.get("price_from", False)),
                "duration_min": x["duration_min"],
                "masters": [names[m] for m in x["master_ids"] if m in names],
            }
        )
    return {"services": out}


async def get_masters(ctx: ToolContext, service_id: int | None = None) -> dict[str, Any]:
    cat = await _catalog(ctx)
    out = []
    for m in cat["masters"]:
        svcs = [
            {"id": x["id"], "name": x["name"]}
            for x in cat["services"]
            if m["id"] in x["master_ids"]
        ]
        if service_id is None or any(x["id"] == service_id for x in svcs):
            out.append({"id": m["id"], "name": m["name"], "services": svcs})
    return {"masters": out}


async def find_free_slots(
    ctx: ToolContext,
    service_id: int,
    date_from: str,
    date_to: str,
    master_id: int | None = None,
) -> dict[str, Any]:
    tz = ctx.settings.zone
    today = ctx.now.astimezone(tz).date()
    d_from = max(_parse_date(date_from), today)
    d_to = max(_parse_date(date_to), d_from)
    d_to = min(d_to, d_from + timedelta(days=MAX_SLOT_RANGE_DAYS - 1))
    cat = await _catalog(ctx)
    service = next((x for x in cat["services"] if x["id"] == service_id), None)
    if service is None:
        raise ToolError("Послугу не знайдено")
    rows = await ctx.mds.slots(service_id, d_from, d_to, master_id)
    per_day: dict[Any, dict[datetime, list[int]]] = defaultdict(dict)
    for start, masters in rows:
        per_day[start.astimezone(tz).date()][start] = masters
    picked = pick_spread(
        per_day, timedelta(minutes=service["duration_min"]), max_slots=ctx.settings.max_slots
    )
    names = {m["id"]: m["name"] for m in cat["masters"]}
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "slots": [
            {
                **_slot_json(x.start_at, ctx.settings),
                "masters": [{"id": m, "name": names.get(m, "")} for m in x.master_ids],
            }
            for x in picked
        ],
    }


def _identity(ctx: ToolContext) -> tuple[Client, Conversation]:
    with Session(ctx.engine, expire_on_commit=False) as s:
        return s.get(Client, ctx.client_id), s.get(Conversation, ctx.conversation_id)


def _ident_payload(client: Client) -> dict[str, Any]:
    return {
        "phone": client.phone,
        "telegram_user_id": client.tg_user_id,
        "instagram_user_id": client.ig_user_id,
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
    client, conv = _identity(ctx)
    phone = normalize_phone(client_phone) if client_phone else client.phone
    if not phone:
        raise ToolError("Для запису потрібен номер телефону. Попроси клієнта його написати")
    with Session(ctx.engine) as s, s.begin():
        c = s.get(Client, ctx.client_id)
        if client_name.strip():
            c.name = client_name.strip()[:100]
        if phone != c.phone:
            c = cl.attach_phone(s, c, phone)
            if c.id != ctx.client_id:
                s.get(Conversation, ctx.conversation_id).client_id = c.id
                ctx.client_id = c.id
        client_name = c.name
        tg, ig = c.tg_user_id, c.ig_user_id
    try:
        a = await ctx.mds.book(
            channel=channel_for(conv.channel),
            service_id=service_id,
            master_id=master_id,
            start_at=start,
            client_name=client_name or "Клієнт",
            client_phone=phone,
            telegram_user_id=tg,
            instagram_user_id=ig,
            external_ref=f"mdm-c{ctx.conversation_id}-s{service_id}-m{master_id}-{int(start.timestamp())}",
            lead_source=ctx.lead_source,
        )
    except MdsError as e:
        if e.code == "slot_taken":
            return {"ok": False, "error": "slot_taken", "message": "Цей час уже зайнятий"}
        raise ToolError(e.message) from e
    ctx.bookings_created.append(a["id"])
    status = "очікує підтвердження майстра" if a["status"] == "pending" else "підтверджено"
    label = _slot_json(start, ctx.settings)["label"]
    summary = f"{client_name}, {a['service_name']}, {label}, {a['master_name']}"
    await ctx.notifier.admin(f"🆕 AI записав у MDS Connect #{a['id']} ({status}): {summary}")
    return {"ok": True, "booking_id": a["id"], "status": status, "summary": summary}


async def get_client_bookings(ctx: ToolContext) -> dict[str, Any]:
    client, _ = _identity(ctx)
    rows = await ctx.mds.lookup(**_ident_payload(client))
    return {
        "bookings": [
            {
                "booking_id": x["id"],
                **_slot_json(ctx.mds.from_local(x["starts_at"]), ctx.settings),
                "service": x["service_name"],
                "master": x["master_name"],
                "status": x["status"],
            }
            for x in rows
        ]
    }


async def cancel_or_reschedule(
    ctx: ToolContext, booking_id: int, new_start_at: str | None = None
) -> dict[str, Any]:
    client, _ = _identity(ctx)
    ident = _ident_payload(client)
    mine = {x["id"]: x for x in await ctx.mds.lookup(**ident)}
    old = mine.get(booking_id)
    if old is None:
        raise ToolError("Серед майбутніх записів клієнта такого немає")
    if new_start_at:
        # Спершу новий запис (якщо час зайнятий — старий лишається), потім скасування старого.
        res = await create_booking(
            ctx, old["service_id"], old["master_id"], new_start_at, client.name, client.phone
        )
        if not res.get("ok"):
            return res
        await ctx.mds.cancel(booking_id, reason="Перенесено клієнтом через AI-помічника", **ident)
        return {"ok": True, "status": "перенесено", "summary": res["summary"]}
    await ctx.mds.cancel(booking_id, **ident)
    await ctx.notifier.admin(f"🚫 AI скасував запис MDS #{booking_id} на прохання клієнта")
    return {"ok": True, "status": "скасовано"}


HANDLERS = {
    "get_services": get_services,
    "get_masters": get_masters,
    "find_free_slots": find_free_slots,
    "create_booking": create_booking,
    "get_client_bookings": get_client_bookings,
    "cancel_or_reschedule": cancel_or_reschedule,
    "handoff_to_human": handoff_to_human,
}

__all__ = ["HANDLERS", "do_handoff"]
