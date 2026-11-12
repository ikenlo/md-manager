"""Звіт «звідки записи»: записи, візити, неявки й виручка за мітками джерел."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Booking, BookingStatus

NO_LABEL = "без мітки"


@dataclass
class SourceRow:
    source: str
    bookings: int = 0
    came: int = 0
    no_show: int = 0
    cancelled: int = 0
    revenue_kop: int = 0
    tagged: bool = False  # джерело — мітка посилання / оголошення, а не «рекомендація» тощо


def _key(v: dict[str, Any]) -> str:
    attr = v.get("attribution") or {}
    return attr.get("lead_source") or attr.get("channel") or v.get("client_source") or NO_LABEL


def aggregate_mds_visits(visits: list[dict[str, Any]]) -> list[SourceRow]:
    rows: dict[str, SourceRow] = defaultdict(lambda: SourceRow(""))
    for v in visits:
        k = _key(v)
        r = rows[k]
        r.source = k
        r.tagged = bool((v.get("attribution") or {}).get("lead_source"))
        r.bookings += 1
        if v["status"] == "completed":
            r.came += 1
            r.revenue_kop += v.get("paid_amount") or 0
        elif v["status"] == "no_show":
            r.no_show += 1
        elif v["status"] == "cancelled":
            r.cancelled += 1
    return sorted(rows.values(), key=lambda r: (-r.revenue_kop, -r.bookings, r.source))


def aggregate_local(session: Session, since: datetime) -> list[SourceRow]:
    rows: dict[str, SourceRow] = defaultdict(lambda: SourceRow(""))
    for b in session.scalars(select(Booking).where(Booking.start_at >= since)):
        k = b.lead_source or b.source.value
        r = rows[k]
        r.source = k
        r.tagged = bool(b.lead_source)
        r.bookings += 1
        r.came += b.status == BookingStatus.completed
        r.no_show += b.status == BookingStatus.no_show
        r.cancelled += b.status == BookingStatus.cancelled
    return sorted(rows.values(), key=lambda r: (-r.bookings, r.source))


def format_sources(rows: list[SourceRow], days: int, spend_kop: int | None = None) -> str:
    if not rows:
        return f"За {days} днів записів немає."
    lines = [f"📈 Джерела записів за {days} днів", ""]
    for r in rows:
        line = f"• {r.source}: записів {r.bookings}, прийшли {r.came}"
        if r.no_show:
            line += f", неявок {r.no_show}"
        if r.cancelled:
            line += f", скасовано {r.cancelled}"
        if r.revenue_kop:
            line += f", виручка {r.revenue_kop // 100} грн"
        lines.append(line)
    total_rev = sum(r.revenue_kop for r in rows)
    if spend_kop is not None:
        lines.append("")
        lines.append(f"Реклама (витрати в MDS): {spend_kop // 100} грн")
        paid = [r for r in rows if r.tagged]
        came = sum(r.came for r in paid)
        if spend_kop and came:
            lines.append(
                f"≈ {spend_kop // 100 // came} грн рекламних витрат на один візит з мітками"
            )
        if spend_kop and total_rev:
            lines.append(f"Виручка / реклама: {total_rev / spend_kop:.1f}×")
    return "\n".join(lines)


def period(now: datetime, days: int) -> tuple[datetime, datetime]:
    return now - timedelta(days=days), now
