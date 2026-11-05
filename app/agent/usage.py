"""Облік токенів і вартості викликів Claude."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AiUsage

# $ за 1 млн токенів (вхід, вихід) для промптів до 100K. Перевіряйте актуальні ціни.
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}
CACHE_READ_MULT = 0.1
CACHE_WRITE_MULT = 1.25


def cost_usd(model: str, inp: int, out: int, cache_read: int = 0, cache_write: int = 0) -> float:
    price_in, price_out = PRICES.get(model, PRICES["claude-sonnet-5-5"])
    return (
        inp * price_in
        + out * price_out
        + cache_read * price_in * CACHE_READ_MULT
        + cache_write * price_in * CACHE_WRITE_MULT
    ) / 1_000_000


def record(session: Session, conversation_id: int | None, model: str, usage: object) -> None:
    session.add(
        AiUsage(
            conversation_id=conversation_id,
            model=model,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )
    )


class UsageReport:
    """Передається в /stats як `usage`."""

    @staticmethod
    def cost_since(session: Session, since: datetime) -> float:
        rows = session.execute(
            select(
                AiUsage.model,
                func.sum(AiUsage.input_tokens),
                func.sum(AiUsage.output_tokens),
                func.sum(AiUsage.cache_read_tokens),
                func.sum(AiUsage.cache_write_tokens),
            )
            .where(AiUsage.created_at >= since)
            .group_by(AiUsage.model)
        )
        return sum(cost_usd(m, i or 0, o or 0, r or 0, w or 0) for m, i, o, r, w in rows)
