"""Заповнює налаштування, послуги, майстрів і графік з seed.yaml.

Ідемпотентно: послуги й майстри шукаються за назвою/іменем і оновлюються,
графік майстра з seed.yaml повністю замінює наявний.
"""

from __future__ import annotations

import sys
from datetime import time
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Master, SalonSetting, Service, WorkSchedule
from app.db.session import session_scope

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def _parse_range(value: str) -> list[tuple[time, time]]:
    """'09:00-18:00' або '09:00-13:00, 14:00-18:00' (перерва)."""
    out = []
    for part in value.split(","):
        start, end = (time.fromisoformat(x.strip()) for x in part.split("-"))
        out.append((start, end))
    return out


def seed(session: Session, data: dict) -> None:
    for key, value in (data.get("settings") or {}).items():
        session.merge(SalonSetting(key=key, value=str(value)))

    services: dict[str, Service] = {}
    for item in data.get("services") or []:
        svc = session.scalar(select(Service).where(Service.name == item["name"]))
        if svc is None:
            svc = Service(name=item["name"])
            session.add(svc)
        svc.category = item.get("category", "")
        svc.price_from = int(item["price_from"])
        svc.price_to = item.get("price_to")
        svc.duration_min = int(item["duration_min"])
        svc.buffer_min = int(item.get("buffer_min", 0))
        svc.is_active = bool(item.get("is_active", True))
        services[svc.name] = svc

    for item in data.get("masters") or []:
        master = session.scalar(select(Master).where(Master.name == item["name"]))
        if master is None:
            master = Master(name=item["name"])
            session.add(master)
        master.tg_user_id = item.get("tg_user_id")
        master.is_active = bool(item.get("is_active", True))
        try:
            master.services = [services[n] for n in item.get("services", [])]
        except KeyError as e:
            raise SystemExit(f"Майстер {item['name']}: невідома послуга {e}") from e
        master.schedule.clear()
        session.flush()
        for day, value in (item.get("schedule") or {}).items():
            for start, end in _parse_range(value):
                master.schedule.append(
                    WorkSchedule(weekday=WEEKDAYS[day], start_time=start, end_time=end)
                )


def main(path: str = "seed.yaml") -> None:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    with session_scope() as session:
        seed(session, data)
    print(f"Seed з {path} застосовано")


if __name__ == "__main__":
    main(*sys.argv[1:])
