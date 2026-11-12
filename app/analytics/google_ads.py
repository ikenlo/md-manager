"""Google Ads API (REST): щоденні витрати, покази, кліки й конверсії кампаній → ad_daily.

Доступ: developer token + OAuth-клієнт + refresh token власника акаунта (docs/MARKETING_ACCESS.md).
Рядок ad_daily для Google — це кампанія (platform="google", ad_id = campaign.id).
Мітка джерела для атрибуції записів — gads_<campaign_id> (t.me/<бот>?start=gads_<id>).
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

import httpx
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import AdDaily

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://googleads.googleapis.com"
LABEL_PREFIX = "gads_"

QUERY = (
    "SELECT segments.date, campaign.id, campaign.name, metrics.impressions, metrics.clicks, "
    "metrics.cost_micros, metrics.conversions FROM campaign "
    "WHERE segments.date BETWEEN '{since}' AND '{until}' AND metrics.impressions > 0"
)


class GoogleAdsError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class GoogleAdsClient:
    def __init__(
        self,
        *,
        developer_token: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        customer_id: str,
        login_customer_id: str = "",
        version: str = "v22",
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.developer_token = developer_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.customer_id = customer_id.replace("-", "")
        self.login_customer_id = login_customer_id.replace("-", "")
        self.version = version
        self.http = http or httpx.AsyncClient(timeout=30)
        self._access: tuple[float, str] | None = None

    async def _token(self) -> str:
        if self._access and self._access[0] > time.monotonic():
            return self._access[1]
        try:
            r = await self.http.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                },
            )
        except httpx.HTTPError as e:
            raise GoogleAdsError(503, "Google недоступний") from e
        data = r.json() if r.content else {}
        if r.status_code >= 400 or "access_token" not in data:
            raise GoogleAdsError(
                r.status_code,
                "Google Ads: не вдалося оновити доступ — перевірте GOOGLE_ADS_REFRESH_TOKEN "
                f"({data.get('error') or r.status_code})",
            )
        ttl = int(data.get("expires_in") or 3600) - 60
        self._access = (time.monotonic() + ttl, data["access_token"])
        return data["access_token"]

    async def campaigns_daily(self, since: date, until: date) -> list[dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {await self._token()}",
            "developer-token": self.developer_token,
        }
        if self.login_customer_id:
            headers["login-customer-id"] = self.login_customer_id
        url = f"{API}/{self.version}/customers/{self.customer_id}/googleAds:search"
        body: dict[str, Any] = {
            "query": QUERY.format(since=since.isoformat(), until=until.isoformat())
        }
        rows: list[dict[str, Any]] = []
        for _ in range(20):  # сторінки
            try:
                r = await self.http.post(url, headers=headers, json=body)
            except httpx.HTTPError as e:
                raise GoogleAdsError(503, "Google Ads недоступний") from e
            data = r.json() if r.content else {}
            if r.status_code >= 400:
                err = data[0] if isinstance(data, list) and data else data
                msg = (err.get("error") or {}).get("message") if isinstance(err, dict) else None
                raise GoogleAdsError(r.status_code, msg or f"Google Ads: помилка {r.status_code}")
            rows.extend(data.get("results") or [])
            nxt = data.get("nextPageToken")
            if not nxt:
                break
            body = {**body, "pageToken": nxt}
        return rows


async def collect(
    engine: Engine, client: GoogleAdsClient, *, today: date, days_back: int = 3
) -> dict[str, int]:
    """Перезібрати останні days_back днів (конверсії Google дораховуються із запізненням)."""
    since, until = today - timedelta(days=days_back), today - timedelta(days=1)
    rows = await client.campaigns_daily(since, until)
    n = 0
    with Session(engine) as s, s.begin():
        for r in rows:
            camp, m, seg = r.get("campaign") or {}, r.get("metrics") or {}, r.get("segments") or {}
            d = date.fromisoformat(seg["date"])
            cid = str(camp["id"])
            ad = s.scalar(
                select(AdDaily).where(
                    AdDaily.day == d, AdDaily.platform == "google", AdDaily.ad_id == cid
                )
            )
            if ad is None:
                ad = AdDaily(day=d, platform="google", ad_id=cid)
                s.add(ad)
            ad.ad_name = (camp.get("name") or "")[:200]
            ad.campaign_name = "Google Ads"
            ad.impressions = int(m.get("impressions") or 0)
            ad.clicks = int(m.get("clicks") or 0)
            # 1 одиниця валюти = 1 000 000 micros = 100 копійок
            ad.spend_minor = round(int(m.get("costMicros") or 0) / 10_000)
            ad.conversations = round(float(m.get("conversions") or 0))
            n += 1
    return {"google_rows": n}
