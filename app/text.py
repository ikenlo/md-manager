"""Форматування і розбір дат/часу/телефонів українською. Без I/O."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.booking.slots import KYIV

WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]
WEEKDAYS_FULL = ["понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота", "неділя"]
MONTHS_GEN = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]  # fmt: skip


def local(dt: datetime, tz: ZoneInfo = KYIV) -> datetime:
    return dt.astimezone(tz)


def fmt_time(dt: datetime, tz: ZoneInfo = KYIV) -> str:
    return local(dt, tz).strftime("%H:%M")


def fmt_slot(dt: datetime, tz: ZoneInfo = KYIV) -> str:
    """'пт 20.11 14:00'"""
    d = local(dt, tz)
    return f"{WEEKDAYS_SHORT[d.weekday()]} {d:%d.%m %H:%M}"


def fmt_date_long(d: date) -> str:
    """'пʼятниця, 20 листопада'"""
    return f"{WEEKDAYS_FULL[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}"


def fmt_price(price_from: int, price_to: int | None) -> str:
    if price_to and price_to != price_from:
        return f"{price_from}–{price_to} грн"
    return f"{price_from} грн"


def relative_day(d: date, today: date) -> str:
    """'сьогодні' / 'завтра' / 'пт 20.11'"""
    if d == today:
        return "сьогодні"
    if d == today + timedelta(days=1):
        return "завтра"
    return f"{WEEKDAYS_SHORT[d.weekday()]} {d:%d.%m}"


class ParseError(ValueError):
    pass


def parse_date(s: str, today: date) -> date:
    """'2026-11-20', '20.11', '20.11.2026', 'сьогодні', 'завтра'.

    Дата без року — найближча в майбутньому (або сьогодні).
    """
    s = s.strip().lower()
    if s in ("сьогодні", "today"):
        return today
    if s in ("завтра", "tomorrow"):
        return today + timedelta(days=1)
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return date.fromisoformat(s)
        m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?", s)
        if m:
            day, month, year = int(m[1]), int(m[2]), m[3]
            if year:
                y = int(year)
                return date(y + 2000 if y < 100 else y, month, day)
            d = date(today.year, month, day)
            return d if d >= today else date(today.year + 1, month, day)
    except ValueError as e:
        raise ParseError(f"Некоректна дата: {s}") from e
    raise ParseError(f"Не розумію дату: {s}. Приклад: 20.11 або 2026-11-20")


def parse_time(s: str) -> time:
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", s.strip())
    if not m:
        raise ParseError(f"Не розумію час: {s}. Приклад: 14:00")
    try:
        return time(int(m[1]), int(m[2]))
    except ValueError as e:
        raise ParseError(f"Некоректний час: {s}") from e


def local_to_utc(d: date, t: time, tz: ZoneInfo = KYIV) -> datetime:
    return datetime.combine(d, t, tzinfo=tz).astimezone(UTC)


def day_bounds_utc(d: date, tz: ZoneInfo = KYIV) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time(0), tzinfo=tz)
    end = datetime.combine(d + timedelta(days=1), time(0), tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def normalize_phone(raw: str) -> str | None:
    """Український номер → +380XXXXXXXXX. Інші міжнародні — +цифри. Сміття → None."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10 and digits.startswith("0"):
        digits = "38" + digits
    elif len(digits) == 9:
        digits = "380" + digits
    if digits.startswith("380") and len(digits) == 12:
        return "+" + digits
    if 10 <= len(digits) <= 15 and raw.strip().startswith("+"):
        return "+" + digits
    return None


def mask_phone(phone: str | None) -> str:
    """Для логів не використовуємо телефони взагалі; для адмінки — повний номер."""
    if not phone:
        return "—"
    return phone
