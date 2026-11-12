"""Черга погоджень: AI ставить дію в чергу, людина підтверджує або відхиляє.

Виконавці реєструються за видом (kind): після «Підтвердити» викликається executor(payload).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.db.models import Approval

Executor = Callable[[dict[str, Any]], Awaitable[None]]
KINDS = {
    "publish_post": "Публікація поста",
    "campaign": "Розсилка",
    "ad": "Реклама",
}


def request(s: Session, kind: str, title: str, payload: dict[str, Any], by: str = "AI") -> Approval:
    a = Approval(kind=kind, title=title[:200], payload=json.dumps(payload, ensure_ascii=False),
                 requested_by=by)  # fmt: skip
    s.add(a)
    s.flush()
    audit(s, by, "approval.request", f"approval:{a.id}", title)
    return a


def pending_count(s: Session) -> int:
    return s.scalar(select(func.count()).where(Approval.status == "pending")) or 0


def listing(s: Session, status: str | None = "pending", limit: int = 100) -> list[dict[str, Any]]:
    q = select(Approval).order_by(Approval.id.desc()).limit(limit)
    if status:
        q = q.where(Approval.status == status)
    return [
        {"id": a.id, "kind": a.kind, "kind_name": KINDS.get(a.kind, a.kind), "title": a.title,
         "payload": json.loads(a.payload or "{}"), "status": a.status,
         "requested_by": a.requested_by, "decided_by": a.decided_by, "reason": a.reason,
         "created_at": a.created_at.isoformat(),
         "decided_at": a.decided_at.isoformat() if a.decided_at else None}
        for a in s.scalars(q)
    ]  # fmt: skip


def decide(s: Session, approval_id: int, approve: bool, by: str, reason: str = "") -> Approval:
    a = s.get(Approval, approval_id)
    if a is None:
        raise ValueError("Погодження не знайдено")
    if a.status != "pending":
        raise ValueError("Це вже вирішено")
    a.status = "approved" if approve else "rejected"
    a.decided_by = by
    a.reason = reason.strip()[:500]
    a.decided_at = datetime.now(UTC)
    audit(s, by, "approval." + a.status, f"approval:{a.id}", a.title)
    return a
