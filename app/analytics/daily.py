"""Статистика за день: салон (MDS Connect), Instagram, Facebook, Meta Ads, Google Ads.

Значення вчорашнього дня порівнюється із середнім за 7 попередніх днів. Тільки агрегати —
жодних імен чи телефонів клієнтів (ці дані йдуть і в AI-аналітика).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import AdDaily, Booking, BookingStatus, MetricDaily

BASELINE_DAYS = 7

# (джерело, метрика, підпис)
SOCIAL = (
    ("instagram", "reach", "Охоплення"),
    ("instagram", "views", "Перегляди"),
    ("instagram", "accounts_engaged", "Залучені акаунти"),
    ("instagram", "total_interactions", "Взаємодії"),
    ("instagram", "profile_links_taps", "Натискання в профілі"),
    ("facebook", "page_media_view", "Перегляди"),
    ("facebook", "page_total_media_view_unique", "Глядачі"),
    ("facebook", "page_post_engagements", "Взаємодії з постами"),
    ("facebook", "page_daily_follows_unique", "Нові підписки"),
)
GROUP_NAMES = {
    "salon": "Салон (MDS Connect)",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "meta_ads": "Реклама Meta",
    "google_ads": "Реклама Google",
}


@dataclass
class StatRow:
    group: str
    key: str
    label: str
    value: float | None
    avg: float | None
    money: bool = False  # копійки

    @property
    def delta(self) -> float | None:
        """Зміна відносно середнього, частка (0.25 = +25%)."""
        if self.value is None or not self.avg:
            return None
        return self.value / self.avg - 1


@dataclass
class DayStats:
    day: date
    rows: list[StatRow]
    followers: int | None = None
    notes: list[str] = field(default_factory=list)

    def groups(self) -> list[tuple[str, list[StatRow]]]:
        out: dict[str, list[StatRow]] = defaultdict(list)
        for r in self.rows:
            out[r.group].append(r)
        return [(g, out[g]) for g in GROUP_NAMES if g in out]

    def as_dict(self) -> dict[str, Any]:
        """Компактно для промпту AI."""

        def fmt(v: float | None, money: bool) -> float | None:
            if v is None:
                return None
            return round(v / 100, 2) if money else round(v, 1)

        return {
            "day": self.day.isoformat(),
            "followers_instagram": self.followers,
            "metrics": [
                {
                    "group": GROUP_NAMES[r.group],
                    "metric": r.label + (", грн" if r.money else ""),
                    "yesterday": fmt(r.value, r.money),
                    "avg_prev_7d": fmt(r.avg, r.money),
                }
                for r in self.rows
            ],
        }


def _avg(by_day: dict[date, float], days: list[date]) -> float | None:
    vals = [by_day[d] for d in days if d in by_day]
    return sum(vals) / len(vals) if vals else None


def _naive_day(s: str | None) -> date | None:
    return datetime.fromisoformat(s).date() if s else None


def salon_rows(visits: list[dict[str, Any]], day: date, base: list[date]) -> list[StatRow]:
    """Візити з MDS (naive-час Києва): нові записи за датою створення, візити за датою візиту."""
    created: dict[date, float] = defaultdict(float)
    planned: dict[date, float] = defaultdict(float)
    came: dict[date, float] = defaultdict(float)
    no_show: dict[date, float] = defaultdict(float)
    revenue: dict[date, float] = defaultdict(float)
    for v in visits:
        c = _naive_day(v.get("created_at"))
        if c is not None:
            created[c] += 1
        d = _naive_day(v.get("starts_at"))
        if d is None or v.get("status") == "cancelled":
            continue
        planned[d] += 1
        if v.get("status") == "completed":
            came[d] += 1
            revenue[d] += v.get("paid_amount") or 0
        elif v.get("status") == "no_show":
            no_show[d] += 1
    all_days = [*base, day]
    for m in (created, planned, came, no_show, revenue):
        for d in all_days:
            m.setdefault(d, 0.0)
    return [
        StatRow("salon", "created", "Нові записи", created[day], _avg(created, base)),
        StatRow("salon", "planned", "Візитів у графіку", planned[day], _avg(planned, base)),
        StatRow("salon", "came", "Прийшли", came[day], _avg(came, base)),
        StatRow("salon", "no_show", "Неявки", no_show[day], _avg(no_show, base)),
        StatRow("salon", "revenue", "Виручка", revenue[day], _avg(revenue, base), money=True),
    ]


def _local_visits(s: Session, settings: Settings, start: date) -> list[dict[str, Any]]:
    """Локальні записи в тому ж форматі, що й /visits MDS (без грошей — їх веде MDS)."""
    tz = settings.zone
    since = datetime.combine(start - timedelta(days=1), datetime.min.time(), tzinfo=tz)
    out = []
    for b in s.scalars(
        select(Booking).where((Booking.start_at >= since) | (Booking.created_at >= since))
    ):
        out.append(
            {
                "starts_at": b.start_at.astimezone(tz).replace(tzinfo=None).isoformat(),
                "created_at": b.created_at.astimezone(tz).replace(tzinfo=None).isoformat(),
                "status": {
                    BookingStatus.completed: "completed",
                    BookingStatus.no_show: "no_show",
                    BookingStatus.cancelled: "cancelled",
                }.get(b.status, "scheduled"),
                "paid_amount": None,
            }
        )
    return out


async def build(engine: Engine, settings: Settings, now: datetime, *, mds: Any = None) -> DayStats:
    day = now.astimezone(settings.zone).date() - timedelta(days=1)
    base = [day - timedelta(days=i) for i in range(BASELINE_DAYS, 0, -1)]
    notes: list[str] = []
    rows: list[StatRow] = []

    visits: list[dict[str, Any]] | None
    if mds is not None:
        try:
            visits = await mds.visits(base[0], day)
        except Exception:  # noqa: BLE001
            visits = None
            notes.append("MDS Connect не відповів — показники салону недоступні.")
    else:
        with Session(engine) as s:
            visits = _local_visits(s, settings, base[0])
    if visits is not None:
        rows += salon_rows(visits, day, base)

    with Session(engine) as s:
        metric_vals: dict[tuple[str, str], dict[date, float]] = defaultdict(dict)
        for m in s.scalars(
            select(MetricDaily).where(MetricDaily.day >= base[0], MetricDaily.day <= day)
        ):
            metric_vals[(m.source, m.metric)][m.day] = m.value
        for source, metric, label in SOCIAL:
            vals = metric_vals.get((source, metric))
            if not vals:
                continue
            rows.append(StatRow(source, metric, label, vals.get(day), _avg(vals, base)))

        ads: dict[tuple[str, str], dict[date, float]] = defaultdict(dict)
        for platform, d, spend, clicks, conv, imp in s.execute(
            select(
                AdDaily.platform,
                AdDaily.day,
                func.sum(AdDaily.spend_minor),
                func.sum(AdDaily.clicks),
                func.sum(AdDaily.conversations),
                func.sum(AdDaily.impressions),
            )
            .where(AdDaily.day >= base[0], AdDaily.day <= day)
            .group_by(AdDaily.platform, AdDaily.day)
        ):
            for key, v in (("spend", spend), ("clicks", clicks), ("conv", conv), ("imp", imp)):
                ads[(platform, key)][d] = float(v or 0)
        for platform, group, conv_label in (
            ("meta", "meta_ads", "Діалоги в Direct"),
            ("google", "google_ads", "Конверсії"),
        ):
            if not any(ads.get((platform, k)) for k in ("spend", "imp")):
                continue
            for key, label, money in (
                ("spend", "Витрати", True),
                ("imp", "Покази", False),
                ("clicks", "Кліки", False),
                ("conv", conv_label, False),
            ):
                vals = ads.get((platform, key), {})
                full = {d: vals.get(d, 0.0) for d in [*base, day]}
                rows.append(StatRow(group, key, label, full[day], _avg(full, base), money))

        followers = s.scalar(
            select(MetricDaily.value)
            .where(MetricDaily.source == "instagram", MetricDaily.metric == "followers_count")
            .order_by(MetricDaily.day.desc())
            .limit(1)
        )
    if any(r.group == "instagram" and r.value is None for r in rows):
        notes.append("Instagram віддає дані із затримкою до 48 год — вчорашні цифри ще зростуть.")
    return DayStats(day, rows, int(followers) if followers is not None else None, notes)
