"""AI Sales Agent: діалог → LLM → (інструменти → LLM)* → відповідь + намір.

Чиста логіка без БД, подій і мережі (окрім адаптера LLM) — тестується з фейковим адаптером.

Інструменти, що змінюють дані (WRITE_TOOLS), агент НЕ виконує: лише перевіряє аргументи й
повертає моделі {"pending_approval": true}. Виконує їх endpoint погодження після рішення людини.
Збій LLM (OllamaError) → запасна відповідь і намір escalate.
"""

import json
import logging
from typing import Any

from app.services.adapters.factory import get_ollama_adapter
from app.services.adapters.ollama_base import OllamaAdapter, OllamaError
from app.services.ai_prompt import load_sales_prompt
from app.services.tools import TOOLS_SCHEMA, ToolError, execute_tool
from app.services.tools.implementations import SERVICES, _parse_date, _parse_time

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3
# Скільки викликів інструментів обробляємо з однієї відповіді моделі (решту ігноруємо)
MAX_TOOL_LOOP = 3

# Інструменти, що змінюють стан (створення/зміна/видалення) — лише через погодження людиною
WRITE_TOOLS = {"create_appointment"}
WRITE_TOOL_REQUIRED = {"create_appointment": {"service_name", "date", "time"}}

FALLBACK_REPLY = "Вибачте, не можу обробити запит. Передам менеджеру."
PENDING_REPLY = (
    "Передала ваш запис адміністратору на підтвердження. Скоро повернемося з відповіддю!"
)
LLM_ERROR_REPLY = "Вибачте, тимчасово не можу відповісти. Передам менеджеру."
PENDING_MESSAGE = (
    "Запис ще НЕ створено: його передано адміністратору на підтвердження. "
    "Повідом клієнта, що адміністратор підтвердить запис найближчим часом."
)
ESCALATE_KEYWORDS = ("менеджер", "передзвон", "покличу", "уточню у", "не можу допомогти")


def _parse_arguments(raw: Any) -> dict[str, Any]:
    """Аргументи інструмента → dict. Рядок JSON розбираємо; усе інше, що не dict, → {}."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _check_write_args(name: str, args: dict[str, Any]) -> str | None:
    """Перевіряє аргументи write-інструмента, не виконуючи його. None — гаразд, інакше помилка."""
    required = WRITE_TOOL_REQUIRED.get(name, set())
    missing = sorted(k for k in required if not str(args.get(k) or "").strip())
    if missing:
        return f"Missing required args: {', '.join(missing)}"
    if name == "create_appointment":
        try:
            _parse_date(str(args["date"]))
            _parse_time(str(args["time"]))
        except ToolError as e:
            return str(e)
        known = {s["name"].casefold() for s in SERVICES}
        if str(args["service_name"]).strip().casefold() not in known:
            names = ", ".join(s["name"] for s in SERVICES)
            return f"Невідома послуга «{args['service_name']}». Доступні: {names}"
    return None


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

    try:
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
            full_messages.append(
                {"role": "assistant", "content": content, "tool_calls": tool_calls}
            )

            for call in tool_calls:
                fn = call.get("function") if isinstance(call, dict) else None
                name = fn.get("name") if isinstance(fn, dict) else None
                if not name:
                    continue
                args = _parse_arguments(fn.get("arguments", {}))
                if name in WRITE_TOOLS:
                    # Не виконуємо: лише перевіряємо й чекаємо рішення людини
                    problem = _check_write_args(name, args)
                    if problem:
                        result: dict[str, Any] = {"error": problem}
                    else:
                        result = {
                            "pending_approval": True,
                            "args": args,
                            "tool": name,
                            "message": PENDING_MESSAGE,
                        }
                        needs_approval = True
                        proposed_booking = {
                            "tool": name,
                            "service_name": args.get("service_name"),
                            "date": args.get("date"),
                            "time": args.get("time"),
                            "arguments": args,
                        }
                else:
                    result = await execute_tool(name, args)
                tool_calls_history.append({"name": name, "arguments": args, "result": result})
                logger.info("AI викликав інструмент %s (помилка: %s)", name, "error" in result)
                full_messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(result, ensure_ascii=False),
                        "name": name,
                    }
                )

        if pending_tools:
            # Ліміт вичерпано, а модель усе ще кличе інструменти — фінальної відповіді немає
            logger.warning("Agent hit max iterations (%d), forcing stop", max_iterations)
            # запис уже чекає погодження — не кажемо клієнту, що «не можемо обробити»
            final_content = last_content or (PENDING_REPLY if needs_approval else FALLBACK_REPLY)
    except OllamaError as e:
        logger.error("AI agent OllamaError: %s", e)
        return {
            "content": LLM_ERROR_REPLY,
            "iterations": iterations,
            "tool_calls_history": tool_calls_history,
            "needs_approval": False,
            "proposed_booking": None,
            "intent": "escalate",
            "error": str(e),
        }

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
