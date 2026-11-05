"""Облік токенів і вартості викликів AI (Claude, Gemini)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import prices
from app.db.models import AiUsage

# Сумісність зі старим кодом/тестами
PRICES = prices.TEXT
cost_usd = prices.text_cost


def record(
    session: Session,
    conversation_id: int | None,
    model: str,
    usage: object,
    *,
    provider: str = "anthropic",
    kind: str = "chat",
) -> AiUsage:
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    cr = getattr(usage, "cache_read_input_tokens", 0) or 0
    cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
    row = AiUsage(
        conversation_id=conversation_id,
        provider=provider,
        kind=kind,
        model=model,
        input_tokens=inp,
        output_tokens=out,
        cache_read_tokens=cr,
        cache_write_tokens=cw,
        cost_usd=prices.text_cost(model, inp, out, cr, cw),
    )
    session.add(row)
    return row


def record_units(
    session: Session, *, provider: str, kind: str, model: str, units: int, cost: float
) -> AiUsage:
    row = AiUsage(provider=provider, kind=kind, model=model, units=units, cost_usd=cost)
    session.add(row)
    return row


class UsageReport:
    """Передається в /stats як `usage`."""

    @staticmethod
    def cost_since(session: Session, since: datetime) -> float:
        return float(
            session.scalar(select(func.sum(AiUsage.cost_usd)).where(AiUsage.created_at >= since))
            or 0.0
        )

    @staticmethod
    def by_provider(session: Session, since: datetime) -> list[tuple[str, str, int, float]]:
        """(провайдер, вид, кількість викликів, $) — для /budget."""
        rows = session.execute(
            select(AiUsage.provider, AiUsage.kind, func.count(), func.sum(AiUsage.cost_usd))
            .where(AiUsage.created_at >= since)
            .group_by(AiUsage.provider, AiUsage.kind)
            .order_by(func.sum(AiUsage.cost_usd).desc())
        )
        return [(p, k, n, float(c or 0)) for p, k, n, c in rows]
