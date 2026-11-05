"""Збір щоденної аналітики з Meta Graph API: Instagram-акаунт і Meta Ads.

Токен — System User з Business Manager (власні акаунти салону, App Review не потрібен).
Instagram віддає дані із затримкою до 48 год, тому щодня перезбираємо кілька останніх днів.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import AdDaily, MetricDaily

log = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com"
IG_DAY_METRICS = ("reach", "views", "profile_links_taps", "accounts_engaged", "total_interactions")
CONVERSATION_ACTION = "onsite_conversion.messaging_conversation_started_7d"


class MetaError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class MetaClient:
    def __init__(self, token: str, version: str = "v26.0", http: httpx.AsyncClient | None = None):
        self.token = token
        self.base = f"{GRAPH}/{version}"
        self.http = http or httpx.AsyncClient(timeout=30)

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            r = await self.http.get(
                url, params=params, headers={"Authorization": f"Bearer {self.token}"}
            )
        except httpx.HTTPError as e:
            raise MetaError(503, "Meta недоступна") from e
        data = r.json() if r.content else {}
        if r.status_code >= 400 or "error" in data:
            msg = (data.get("error") or {}).get("message") or f"Meta: помилка {r.status_code}"
            raise MetaError(r.status_code, msg)
        return data

    async def ig_day(self, ig_user_id: str, day: date, tz: ZoneInfo) -> dict[str, float]:
        """Метрики акаунта за одну київську добу."""
        start = int(datetime.combine(day, datetime.min.time(), tzinfo=tz).timestamp())
        data = await self._get(
            f"{self.base}/{ig_user_id}/insights",
            {
                "metric": ",".join(IG_DAY_METRICS),
                "period": "day",
                "metric_type": "total_value",
                "since": start,
                "until": start + 86400,
            },
        )
        out: dict[str, float] = {}
        for row in data.get("data") or []:
            if "total_value" in row:
                out[row["name"]] = float((row["total_value"] or {}).get("value") or 0)
            elif row.get("values"):
                out[row["name"]] = float(row["values"][-1].get("value") or 0)
        return out

    async def ig_followers(self, ig_user_id: str) -> int:
        data = await self._get(f"{self.base}/{ig_user_id}", {"fields": "followers_count"})
        return int(data.get("followers_count") or 0)

    async def ads_daily(self, ad_account_id: str, since: date, until: date) -> list[dict[str, Any]]:
        params: dict[str, Any] | None = {
            "level": "ad",
            "fields": "ad_id,ad_name,campaign_name,impressions,reach,clicks,spend,actions",
            "time_range": json.dumps({"since": since.isoformat(), "until": until.isoformat()}),
            "time_increment": 1,
            "limit": 500,
        }
        url = f"{self.base}/act_{ad_account_id}/insights"
        rows: list[dict[str, Any]] = []
        for _ in range(20):  # сторінки
            data = await self._get(url, params)
            rows.extend(data.get("data") or [])
            nxt = (data.get("paging") or {}).get("next")
            if not nxt:
                break
            url, params = nxt, None
        return rows


def _upsert_metric(s: Session, day: date, source: str, metric: str, value: float) -> None:
    row = s.scalar(
        select(MetricDaily).where(
            MetricDaily.day == day, MetricDaily.source == source, MetricDaily.metric == metric
        )
    )
    if row is None:
        s.add(MetricDaily(day=day, source=source, metric=metric, value=value))
    else:
        row.value = value


def _minor(amount: str | float | None) -> int:
    return round(float(amount or 0) * 100)


def _conversations(actions: list[dict[str, Any]] | None) -> int:
    return sum(
        int(float(a.get("value") or 0))
        for a in actions or []
        if a.get("action_type") == CONVERSATION_ACTION
    )


async def collect(
    engine: Engine,
    client: MetaClient,
    *,
    today: date,
    tz: ZoneInfo,
    ig_user_id: str = "",
    ad_account_id: str = "",
    days_back: int = 3,
) -> dict[str, int]:
    """Зібрати й зберегти дані за останні days_back днів (без сьогоднішнього, він неповний)."""
    days = [today - timedelta(days=i) for i in range(days_back, 0, -1)]
    stats = {"ig_days": 0, "ad_rows": 0}
    if ig_user_id:
        for d in days:
            values = await client.ig_day(ig_user_id, d, tz)
            with Session(engine) as s, s.begin():
                for metric, value in values.items():
                    _upsert_metric(s, d, "instagram", metric, value)
            stats["ig_days"] += 1
        followers = await client.ig_followers(ig_user_id)
        with Session(engine) as s, s.begin():
            _upsert_metric(s, today, "instagram", "followers_count", followers)
    if ad_account_id:
        rows = await client.ads_daily(ad_account_id, days[0], days[-1])
        with Session(engine) as s, s.begin():
            for r in rows:
                d = date.fromisoformat(r["date_start"])
                ad = s.scalar(
                    select(AdDaily).where(
                        AdDaily.day == d, AdDaily.platform == "meta", AdDaily.ad_id == r["ad_id"]
                    )
                )
                if ad is None:
                    ad = AdDaily(day=d, platform="meta", ad_id=r["ad_id"])
                    s.add(ad)
                ad.ad_name = (r.get("ad_name") or "")[:200]
                ad.campaign_name = (r.get("campaign_name") or "")[:200]
                ad.impressions = int(r.get("impressions") or 0)
                ad.reach = int(r.get("reach") or 0)
                ad.clicks = int(r.get("clicks") or 0)
                ad.spend_minor = _minor(r.get("spend"))
                ad.conversations = _conversations(r.get("actions"))
                stats["ad_rows"] += 1
    return stats
