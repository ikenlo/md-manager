"""Виклик Claude зі строгою JSON-відповіддю (structured outputs) + облік витрат і бюджету."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.agent import usage
from app.ai import budget, prices
from app.config import Settings

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AiUnavailable(Exception):
    """Зрозуміла власнику причина, чому AI не відповів (показується на сайті)."""


def obj(props: dict[str, Any]) -> dict[str, Any]:
    """Обʼєкт JSON-схеми: усі поля обовʼязкові, зайвих немає (вимога structured outputs)."""
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


def _has_server_fallback(model: str) -> bool:
    # серверний fallback при відмові є в Opus/Sonnet/Fable, у Haiku — ні
    return "haiku" not in model


async def ask_json(
    claude: Any,
    engine: Engine,
    settings: Settings,
    clock: Callable[[], datetime],
    *,
    model: str,
    effort: str,
    system: str,
    content: str | list[dict[str, Any]],
    schema: dict[str, Any],
    expect_out: int,
    kind: str,
    est_in: int | None = None,
) -> tuple[dict[str, Any], str, float]:
    """Повертає (дані, модель, що відповіла, вартість $). Кидає AiUnavailable / BudgetExceeded."""
    if claude is None:
        raise AiUnavailable("Потрібен ANTHROPIC_API_KEY")
    if est_in is None:
        est_in = (len(system) + len(content if isinstance(content, str) else "")) // 2
    with Session(engine) as s:
        budget.check(
            s,
            settings.ai_monthly_budget_usd,
            clock(),
            settings.zone,
            prices.text_cost(model, est_in, expect_out),
        )
    extra: dict[str, Any] = {}
    if _has_server_fallback(model):
        extra = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
    async with claude.beta.messages.stream(
        model=model,
        max_tokens=64000,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        **extra,
    ) as stream:
        msg = await stream.get_final_message()
    served = getattr(msg, "model", None) or model
    with Session(engine) as s, s.begin():
        cost = usage.record(s, None, served, msg.usage, kind=kind).cost_usd
    if msg.stop_reason == "refusal":
        raise AiUnavailable("Модель відмовилась відповідати — спробуйте пізніше")
    if msg.stop_reason == "max_tokens":
        raise AiUnavailable("Відповідь обірвалась (ліміт токенів) — спробуйте ще раз")
    text = next((b.text for b in msg.content if b.type == "text"), "")
    try:
        return json.loads(text), served, cost
    except ValueError as e:
        raise AiUnavailable("AI повернув некоректну відповідь") from e
