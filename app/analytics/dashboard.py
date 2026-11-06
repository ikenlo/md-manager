"""Дані для панелі власника: джерела записів, реклама з ціною візиту, Instagram, витрати на AI."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import marketing
from app.agent.usage import UsageReport
from app.ai.budget import month_start
from app.config import Settings
from app.db.models import AdDaily, MetricDaily


@dataclass
class AdRow:
    ad_id: str
    name: str
    campaign: str
    spend_minor: int
    impressions: int
    clicks: int
    conversations: int
    bookings: int = 0
    came: int = 0
    revenue_kop: int = 0
    platform: str = "meta"

    @property
    def label(self) -> str:
        """Мітка джерела, за якою записи привʼязуються до оголошення / кампанії."""
        return f"gads_{self.ad_id}" if self.platform == "google" else f"ig_ad_{self.ad_id}"

    @property
    def cost_per_visit_minor(self) -> int | None:
        return self.spend_minor // self.came if self.came else None


@dataclass
class Dashboard:
    days: int
    date_from: date
    date_to: date
    sources: list[marketing.SourceRow]
    totals: dict[str, int]
    ads: list[AdRow]
    ad_spend_minor: int
    ig_series: dict[str, list[tuple[date, float]]]
    followers: int | None
    ai_month: list[tuple[str, str, int, float]]
    ai_month_total: float
    ai_budget: float
    notes: list[str] = field(default_factory=list)


async def build(
    engine: Engine, settings: Settings, now: datetime, *, mds: Any = None, days: int = 30
) -> Dashboard:
    tz = settings.zone
    d_to = now.astimezone(tz).date()
    d_from = d_to - timedelta(days=days - 1)
    notes: list[str] = []

    if mds is not None:
        try:
            sources = marketing.aggregate_mds_visits(await mds.visits(d_from, d_to))
        except Exception:  # noqa: BLE001
            sources = []
            notes.append("MDS Connect не відповів — записи й виручка тимчасово недоступні.")
    else:
        with Session(engine) as s:
            since = datetime.combine(d_from, datetime.min.time(), tzinfo=tz)
            sources = marketing.aggregate_local(s, since)

    totals = {
        "bookings": sum(r.bookings for r in sources),
        "came": sum(r.came for r in sources),
        "no_show": sum(r.no_show for r in sources),
        "revenue_kop": sum(r.revenue_kop for r in sources),
    }
    by_label = {r.source: r for r in sources}

    with Session(engine) as s:
        agg = s.execute(
            select(
                AdDaily.platform,
                AdDaily.ad_id,
                func.max(AdDaily.ad_name),
                func.max(AdDaily.campaign_name),
                func.sum(AdDaily.spend_minor),
                func.sum(AdDaily.impressions),
                func.sum(AdDaily.clicks),
                func.sum(AdDaily.conversations),
            )
            .where(AdDaily.day >= d_from, AdDaily.day <= d_to)
            .group_by(AdDaily.platform, AdDaily.ad_id)
        ).all()
        ads = []
        for platform, ad_id, name, camp, spend, imp, clk, conv in agg:
            row = AdRow(ad_id, name or ad_id, camp or "", spend or 0, imp or 0, clk or 0, conv or 0)
            row.platform = platform
            src = by_label.get(row.label)
            if src:
                row.bookings, row.came, row.revenue_kop = src.bookings, src.came, src.revenue_kop
            ads.append(row)
        ads.sort(key=lambda a: -a.spend_minor)

        series: dict[str, list[tuple[date, float]]] = defaultdict(list)
        for m in s.scalars(
            select(MetricDaily)
            .where(
                MetricDaily.source == "instagram",
                MetricDaily.day >= d_from,
                MetricDaily.metric.in_(("reach", "views", "profile_links_taps")),
            )
            .order_by(MetricDaily.day)
        ):
            series[m.metric].append((m.day, m.value))
        followers = s.scalar(
            select(MetricDaily.value)
            .where(MetricDaily.source == "instagram", MetricDaily.metric == "followers_count")
            .order_by(MetricDaily.day.desc())
            .limit(1)
        )
        ai_rows = UsageReport.by_provider(s, month_start(now, tz))

    if not settings.meta_token:
        notes.append("Meta не підключено — охоплення й реклама з’являться після META_TOKEN.")
    return Dashboard(
        days=days,
        date_from=d_from,
        date_to=d_to,
        sources=sources,
        totals=totals,
        ads=ads,
        ad_spend_minor=sum(a.spend_minor for a in ads),
        ig_series=dict(series),
        followers=int(followers) if followers is not None else None,
        ai_month=ai_rows,
        ai_month_total=sum(r[3] for r in ai_rows),
        ai_budget=settings.ai_monthly_budget_usd,
        notes=notes,
    )
