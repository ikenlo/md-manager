"""Виконання інструмента за назвою: результат або {"error": …} — без винятків назовні."""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.services.tools.implementations import (
    ToolError,
    create_appointment,
    get_services,
    get_slots,
)

log = logging.getLogger("mds.tools")

TOOLS: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "get_services": get_services,
    "get_slots": get_slots,
    "create_appointment": create_appointment,
}


async def execute_tool(name: str, arguments: dict[str, Any] | str | None) -> dict[str, Any]:
    if name not in TOOLS:
        return {"error": f"Unknown tool: {name}"}
    # Деякі моделі віддають аргументи рядком JSON або null
    if arguments is None or arguments == "":
        arguments = {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return {"error": f"Invalid arguments for {name}: not valid JSON"}
    if not isinstance(arguments, dict):
        return {"error": f"Invalid arguments for {name}: expected an object"}

    fn = TOOLS[name]
    try:
        return await fn(**arguments)
    except ToolError as e:
        return {"error": str(e)}
    except TypeError as e:
        return {"error": f"Invalid arguments for {name}: {e}"}
    except Exception as e:
        log.exception("Інструмент %s впав", name)
        return {"error": f"Tool {name} failed: {e}"}
