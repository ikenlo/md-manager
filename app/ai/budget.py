"""Місячний бюджет на AI: перевірка перед кожним платним викликом генерації контенту."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.agent.usage import UsageReport


class BudgetExceeded(Exception):
    pass


def month_start(now: datetime, tz: ZoneInfo) -> datetime:
    local = now.astimezone(tz)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def spent_this_month(session: Session, now: datetime, tz: ZoneInfo) -> float:
    return UsageReport.cost_since(session, month_start(now, tz))


def check(session: Session, limit_usd: float, now: datetime, tz: ZoneInfo, upcoming: float) -> None:
    """Кидає BudgetExceeded, якщо цей виклик вийде за місячний ліміт (0 — без ліміту)."""
    if limit_usd <= 0:
        return
    spent = spent_this_month(session, now, tz)
    if spent + upcoming > limit_usd:
        raise BudgetExceeded(
            f"Місячний ліміт на AI ${limit_usd:.2f}: витрачено ${spent:.2f}, "
            f"цей запит ≈ ${upcoming:.2f}. Підніміть AI_MONTHLY_BUDGET_USD або зачекайте."
        )
