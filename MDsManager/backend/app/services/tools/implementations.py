"""Інструменти AI — Phase 3: фіксовані дані (mock). Phase 4: реальний MDS Connect API.

Помилки, які AI має побачити й пояснити клієнту, — ToolError з українським текстом.
"""

import re
from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4


class ToolError(Exception):
    """Невірні аргументи або бізнес-помилка інструмента (текст іде моделі)."""


SERVICES: list[dict[str, Any]] = [
    {"name": "Манікюр", "price_uah": 350, "duration_min": 60},
    {"name": "Педикюр", "price_uah": 400, "duration_min": 75},
    {"name": "Нарощування нігтів", "price_uah": 800, "duration_min": 120},
    {"name": "Стрижка", "price_uah": 250, "duration_min": 45},
    {"name": "Фарбування", "price_uah": 1200, "duration_min": 180},
    {"name": "Укладка", "price_uah": 300, "duration_min": 60},
    {"name": "Корекція брів", "price_uah": 200, "duration_min": 30},
    {"name": "Нарощування вій", "price_uah": 900, "duration_min": 120},
]

MOCK_SLOTS = ["09:00", "10:30", "13:00", "15:30", "17:00"]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _parse_date(value: str) -> str:
    """Перевіряє YYYY-MM-DD (і що така дата існує, напр. не 2026-02-30)."""
    v = value.strip()
    try:
        if not _DATE_RE.match(v):
            raise ValueError
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise ToolError("Дата має бути у форматі YYYY-MM-DD") from None
    return v


def _parse_time(value: str) -> str:
    v = value.strip()
    try:
        if not _TIME_RE.match(v):
            raise ValueError
        datetime.strptime(v, "%H:%M")
    except ValueError:
        raise ToolError("Час має бути у форматі HH:MM (наприклад, 10:30)") from None
    return v


def _tomorrow() -> str:
    # Локальна дата сервера (ПК салону — Київ)
    return (date_cls.today() + timedelta(days=1)).isoformat()


async def get_services() -> dict[str, Any]:
    return {"services": [dict(s) for s in SERVICES]}


async def get_slots(date: str | None = None) -> dict[str, Any]:
    day = _parse_date(date) if date else _tomorrow()
    return {"date": day, "slots": list(MOCK_SLOTS)}


async def create_appointment(service_name: str, date: str, time: str) -> dict[str, Any]:
    for label, value in (("послугу", service_name), ("дату", date), ("час", time)):
        if not isinstance(value, str) or not value.strip():
            raise ToolError(f"Не вказано {label}")
    day = _parse_date(date)
    at = _parse_time(time)
    name = service_name.strip()
    known = {s["name"].casefold(): s["name"] for s in SERVICES}
    if name.casefold() not in known:
        raise ToolError(
            f"Невідома послуга «{name}». Доступні: " + ", ".join(s["name"] for s in SERVICES)
        )
    return {
        "ok": True,
        "booking_id": "mock_" + uuid4().hex[:8],
        "service_name": known[name.casefold()],
        "date": day,
        "time": at,
        "message": "Запис створено (mock, Phase 3)",
    }
