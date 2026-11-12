"""Щоденна аналітика з Meta Graph API: Instagram (акаунт і пости), сторінка Facebook, Meta Ads.

Токен — System User з Business Manager (власні акаунти салону, App Review не потрібен).
Instagram віддає дані із затримкою до 48 год, тому щодня перезбираємо кілька останніх днів.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import AdDaily, MetricDaily, PostStat

log = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com"
IG_DAY_METRICS = ("reach", "views", "profile_links_taps", "accounts_engaged", "total_interactions")
# Meta з 11.2025 замінила page_impressions* на «перегляди» (page_media_view*)
FB_DAY_METRICS = (
    "page_media_view",
    "page_total_media_view_unique",
    "page_post_engagements",
    "page_daily_follows_unique",
)
IG_MEDIA_FIELDS = (
    "id,caption,media_type,media_product_type,timestamp,permalink,like_count,comments_count"
)
IG_MEDIA_METRICS = ("reach", "views", "saved", "shares")
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
        self._page_tokens: dict[str, str] = {}

    async def _get(
        self, url: str, params: dict[str, Any] | None = None, token: str | None = None
    ) -> dict[str, Any]:
        try:
            r = await self.http.get(
                url, params=params, headers={"Authorization": f"Bearer {token or self.token}"}
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

    async def fb_day(self, page_id: str, day: date, tz: ZoneInfo) -> dict[str, float]:
        """Метрики сторінки Facebook за київську добу. Невідому метрику пропускаємо."""
        token = await self._page_token(page_id)
        start = int(datetime.combine(day, datetime.min.time(), tzinfo=tz).timestamp())

        async def fetch(metrics: tuple[str, ...]) -> dict[str, float]:
            data = await self._get(
                f"{self.base}/{page_id}/insights",
                {"metric": ",".join(metrics), "period": "day", "since": start,
                 "until": start + 86400},
                token,
            )  # fmt: skip
            out: dict[str, float] = {}
            for row in data.get("data") or []:
                vals = row.get("values") or []
                if vals:
                    out[row["name"]] = float(vals[-1].get("value") or 0)
            return out

        try:
            return await fetch(FB_DAY_METRICS)
        except MetaError as e:
            if e.status != 400:
                raise
        out: dict[str, float] = {}
        for m in FB_DAY_METRICS:
            try:
                out.update(await fetch((m,)))
            except MetaError as e:
                if e.status != 400:
                    raise
                log.warning("facebook metric unavailable: %s", m)
        return out

    async def _page_token(self, page_id: str) -> str:
        # токен System User → токен сторінки (insights сторінки вимагають саме його)
        if page_id not in self._page_tokens:
            data = await self._get(f"{self.base}/{page_id}", {"fields": "access_token"})
            self._page_tokens[page_id] = data.get("access_token") or self.token
        return self._page_tokens[page_id]

    async def ig_media(self, ig_user_id: str, limit: int = 15) -> list[dict[str, Any]]:
        """Останні пости з лайками/коментарями та insights (охоплення, перегляди, збереження)."""
        data = await self._get(
            f"{self.base}/{ig_user_id}/media", {"fields": IG_MEDIA_FIELDS, "limit": limit}
        )
        items = data.get("data") or []
        for it in items:
            try:
                ins = await self._get(
                    f"{self.base}/{it['id']}/insights", {"metric": ",".join(IG_MEDIA_METRICS)}
                )
            except MetaError as e:
                if e.status != 400:  # старі пости / сторіс без insights
                    raise
                ins = {}
            it["insights"] = {
                r["name"]: float((r.get("values") or [{}])[-1].get("value") or 0)
                if r.get("values")
                else float((r.get("total_value") or {}).get("value") or 0)
                for r in ins.get("data") or []
            }
        return items

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


def save_post(s: Session, platform: str, it: dict[str, Any]) -> None:
    row = s.scalar(
        select(PostStat).where(PostStat.platform == platform, PostStat.post_id == it["id"])
    )
    if row is None:
        row = PostStat(platform=platform, post_id=it["id"])
        s.add(row)
    ins = it.get("insights") or {}
    row.published_at = datetime.fromisoformat(it["timestamp"].replace("+0000", "+00:00"))
    kind = it.get("media_product_type") or ""
    row.media_type = ("REELS" if kind == "REELS" else it.get("media_type") or "")[:32]
    row.caption = (it.get("caption") or "")[:300]
    row.permalink = (it.get("permalink") or "")[:300]
    row.likes = int(it.get("like_count") or 0)
    row.comments = int(it.get("comments_count") or 0)
    row.reach = int(ins.get("reach") or 0)
    row.views = int(ins.get("views") or 0)
    row.saved = int(ins.get("saved") or 0)
    row.shares = int(ins.get("shares") or 0)
    row.fetched_at = datetime.now(UTC)


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
    page_id: str = "",
    days_back: int = 3,
) -> dict[str, int]:
    """Зібрати й зберегти дані за останні days_back днів (без сьогоднішнього, він неповний)."""
    days = [today - timedelta(days=i) for i in range(days_back, 0, -1)]
    stats = {"ig_days": 0, "ad_rows": 0}
    if page_id:
        stats["fb_days"] = 0
        for d in days:
            values = await client.fb_day(page_id, d, tz)
            with Session(engine) as s, s.begin():
                for metric, value in values.items():
                    _upsert_metric(s, d, "facebook", metric, value)
            stats["fb_days"] += 1
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
        media = await client.ig_media(ig_user_id)
        with Session(engine) as s, s.begin():
            for it in media:
                save_post(s, "instagram", it)
        stats["posts"] = len(media)
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
