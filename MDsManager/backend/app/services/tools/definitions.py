"""JSON-схеми інструментів для function calling Ollama (формат OpenAI-подібний)."""

from typing import Any

TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_services",
            "description": (
                "Повертає список послуг салону з цінами (у гривнях) і тривалістю (у хвилинах)."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_slots",
            "description": "Повертає вільні слоти для запису на вказану дату.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Дата у форматі YYYY-MM-DD. Якщо не вказано — завтра.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_appointment",
            "description": (
                "Створює запис клієнта. Викликати ТІЛЬКИ після явного підтвердження клієнта."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {"type": "string", "description": "Назва послуги"},
                    "date": {"type": "string", "description": "Дата YYYY-MM-DD"},
                    "time": {"type": "string", "description": "Час HH:MM"},
                },
                "required": ["service_name", "date", "time"],
            },
        },
    },
]
