"""Журнал дій. Пишемо коротко й без персональних даних клієнтів (телефонів, переписки)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog


def audit(s: Session, actor: str, action: str, target: str = "", details: str = "") -> None:
    s.add(
        AuditLog(actor=actor[:120], action=action[:64], target=target[:120], details=details[:500])
    )


def recent(s: Session, limit: int = 100) -> list[dict[str, Any]]:
    rows = s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
    return [
        {"id": r.id, "at": r.at.isoformat(), "actor": r.actor, "action": r.action,
         "target": r.target, "details": r.details}
        for r in rows
    ]  # fmt: skip
