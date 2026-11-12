"""AI Sales Agent: діалог → LLM → (інструменти → LLM)* → відповідь + намір.

Чиста логіка без БД, подій і мережі (окрім адаптера LLM) — тестується з фейковим адаптером.
Помилки LLM (OllamaError) не перехоплюються: що робити зі збоєм, вирішує викликач (2.3).
"""

import json
import logging
from typing import Any

from app.services.adapters.factory import get_ollama_adapter
from app.services.adapters.ollama_base import OllamaAdapter
from app.services.ai_prompt import load_sales_prompt
from app.services.tools import TOOLS_SCHEMA, execute_tool

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3
# Скільки викликів інструментів обробляємо з однієї відповіді моделі (решту ігноруємо)
MAX_TOOL_LOOP = 3

FALLBACK_REPLY = "Вибачте, не можу обробити запит. Передам менеджеру."
ESCALATE_KEYWORDS = ("менеджер", "передзвон", "покличу", "уточню у", "не можу допомогти")


def _parse_arguments(raw: Any) -> dict[str, Any]:
    """Аргументи інструмента → dict. Рядок JSON розбираємо; усе інше, що не dict, → {}."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


async def run_agent(
    messages: list[dict[str, Any]],
    adapter: OllamaAdapter | None = None,
    max_iterations: int = MAX_ITERATIONS,
) -> dict[str, Any]:
    """Прогоняє розмову через модель з інструментами.

    messages: історія без system — [{"role": "user"|"assistant", "content": str}].
    Повертає: content, iterations, tool_calls_history, needs_approval, proposed_booking, intent.
    """
    if adapter is None:
        adapter = get_ollama_adapter()

    full_messages: list[dict[str, Any]] = [
        {"role": "system", "content": load_sales_prompt()},
        *messages,
    ]
    tool_calls_history: list[dict[str, Any]] = []
    needs_approval = False
    proposed_booking: dict[str, Any] | None = None
    iterations = 0
    final_content = ""
    last_content = ""
    pending_tools = False

    while iterations < max_iterations:
        iterations += 1
        response = await adapter.chat(full_messages, tools=TOOLS_SCHEMA)
        content = (response.get("content") or "").strip()
        tool_calls = response.get("tool_calls") or []
        last_content = content or last_content

        if not tool_calls:
            final_content = content
            pending_tools = False
            if content:
                full_messages.append({"role": "assistant", "content": content})
            break

        pending_tools = True
        if len(tool_calls) > MAX_TOOL_LOOP:
            logger.warning(
                "Модель повернула %d викликів інструментів, обробляю перші %d",
                len(tool_calls),
                MAX_TOOL_LOOP,
            )
            tool_calls = tool_calls[:MAX_TOOL_LOOP]
        full_messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})

        for call in tool_calls:
            fn = call.get("function") if isinstance(call, dict) else None
            name = fn.get("name") if isinstance(fn, dict) else None
            if not name:
                continue
            args = _parse_arguments(fn.get("arguments", {}))
            result = await execute_tool(name, args)
            tool_calls_history.append({"name": name, "arguments": args, "result": result})
            logger.info("AI викликав інструмент %s (помилка: %s)", name, "error" in result)

            if name == "create_appointment" and not result.get("error"):
                needs_approval = True
                proposed_booking = {
                    "service_name": args.get("service_name"),
                    "date": args.get("date"),
                    "time": args.get("time"),
                    "result": result,
                }
            full_messages.append(
                {"role": "tool", "content": json.dumps(result, ensure_ascii=False), "name": name}
            )

    if pending_tools:
        # Ліміт вичерпано, а модель усе ще кличе інструменти — фінальної відповіді немає
        logger.warning("Agent hit max iterations (%d), forcing stop", max_iterations)
        final_content = last_content or FALLBACK_REPLY

    return {
        "content": final_content,
        "iterations": iterations,
        "tool_calls_history": tool_calls_history,
        "needs_approval": needs_approval,
        "proposed_booking": proposed_booking,
        "intent": _detect_intent(needs_approval, final_content, tool_calls_history),
    }


def _detect_intent(needs_approval: bool, content: str, tool_calls_history: list[dict]) -> str:
    """booking — запис на погодження; escalate — передати людині; question — звичайна відповідь."""
    if needs_approval:
        return "booking"
    content_lower = content.lower()
    if any(kw in content_lower for kw in ESCALATE_KEYWORDS):
        return "escalate"
    if content:
        return "question"
    return "unknown"


def build_messages_from_dialogue(dialogue: Any, limit: int = 10) -> list[dict[str, str]]:
    """Останні `limit` повідомлень діалогу → [{role, content}] для run_agent.

    client → user, agent/human → assistant; системні й порожні пропускаються.
    """
    ordered = sorted(dialogue.messages, key=lambda m: (m.created_at, getattr(m, "id", None) or 0))[
        -limit:
    ]
    result: list[dict[str, str]] = []
    for m in ordered:
        if m.sender_type == "client":
            role = "user"
        elif m.sender_type in ("agent", "human"):
            role = "assistant"
        else:
            continue
        if m.content:
            result.append({"role": role, "content": m.content})
    return result
