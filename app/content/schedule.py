"""Слоти контент-плану на місяць. Дати рахує код — AI лише наповнює їх ідеями."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Slot:
    day: date
    kind: str  # post | story


def month_slots(month: date, *, post_weekday: int = 3, story_every: int = 2) -> list[Slot]:
    """Пост щотижня в post_weekday; сторіс з 1-го числа кожні story_every днів."""
    first = month.replace(day=1)
    days = calendar.monthrange(first.year, first.month)[1]
    out: list[Slot] = []
    for i in range(days):
        d = first + timedelta(days=i)
        if d.weekday() == post_weekday:
            out.append(Slot(d, "post"))
        if story_every > 0 and i % story_every == 0:
            out.append(Slot(d, "story"))
    return sorted(out, key=lambda s: (s.day, s.kind != "post"))
