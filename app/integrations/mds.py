"""Клієнт службового API MDS Connect (/api/ext/v1).

MDS Connect — джерело правди для записів, клієнтів і грошей. Тут лише перетворення:
MDS працює в naive-часі салону (Київ) і копійках; у нас — aware UTC і гривні.
"""

from __future__ import annotations

import time as _time
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.booking.slots import KYIV


class MdsError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class MdsClient:
    CATALOG_TTL_S = 300

    def __init__(
        self,
        base_url: str,
        token: str,
        http: httpx.AsyncClient | None = None,
        tz: ZoneInfo = KYIV,
    ) -> None:
        self.base = base_url.rstrip("/") + "/api/ext/v1"
        self.headers = {"X-MDS-Integration-Token": token}
        self.http = http or httpx.AsyncClient(timeout=15)
        self.tz = tz
        self._catalog: tuple[float, dict[str, Any]] | None = None

    # --- час -------------------------------------------------------------------
    def to_local(self, dt: datetime) -> str:
        """aware → naive Київ у форматі MDS."""
        return dt.astimezone(self.tz).replace(tzinfo=None).isoformat(timespec="minutes")

    def from_local(self, s: str) -> datetime:
        return datetime.fromisoformat(s).replace(tzinfo=self.tz).astimezone(UTC)

    # --- HTTP ------------------------------------------------------------------
    async def _req(self, method: str, path: str, **kw: Any) -> Any:
        try:
            r = await self.http.request(method, self.base + path, headers=self.headers, **kw)
        except httpx.HTTPError as e:
            raise MdsError(503, "unavailable", "MDS Connect недоступний") from e
        if r.status_code >= 400:
            try:
                body = r.json()
            except ValueError:
                body = {}
            raise MdsError(
                r.status_code,
                str(body.get("error") or body.get("code") or "error"),
                str(body.get("detail") or body.get("message") or "Помилка MDS Connect"),
            )
        return r.json()

    # --- каталог і слоти ------------------------------------------------------
    async def catalog(self) -> dict[str, Any]:
        now = _time.monotonic()
        if self._catalog and now - self._catalog[0] < self.CATALOG_TTL_S:
            return self._catalog[1]
        data = await self._req("GET", "/catalog")
        self._catalog = (now, data)
        return data

    async def slots(
        self, service_id: int, date_from: date, date_to: date, master_id: int | None = None
    ) -> list[tuple[datetime, list[int]]]:
        params: dict[str, Any] = {
            "service_id": service_id,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        }
        if master_id:
            params["master_id"] = master_id
        rows = await self._req("GET", "/slots", params=params)
        return [(self.from_local(x["starts_at"]), list(x["master_ids"])) for x in rows]

    # --- записи ---------------------------------------------------------------
    async def book(
        self,
        *,
        channel: str,
        service_id: int,
        master_id: int,
        start_at: datetime,
        client_name: str,
        client_phone: str,
        telegram_user_id: int | None = None,
        instagram_user_id: str | None = None,
        external_ref: str | None = None,
        lead_source: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "channel": channel,
            "service_id": service_id,
            "master_id": master_id,
            "starts_at": self.to_local(start_at),
            "client": {
                "name": client_name,
                "phone": client_phone,
                "telegram_user_id": telegram_user_id,
                "instagram_user_id": instagram_user_id,
            },
            "external_ref": external_ref,
            "attribution": {"lead_source": lead_source} if lead_source else None,
        }
        return await self._req("POST", "/appointments", json=body)

    async def lookup(self, **identity: Any) -> list[dict[str, Any]]:
        return await self._req("POST", "/appointments/lookup", json=identity)

    async def cancel(
        self, appt_id: int, reason: str | None = None, **identity: Any
    ) -> dict[str, Any]:
        return await self._req(
            "POST", f"/appointments/{appt_id}/cancel", json={**identity, "reason": reason}
        )

    # --- аналітика ------------------------------------------------------------
    async def visits(self, date_from: date, date_to: date) -> list[dict[str, Any]]:
        return await self._req(
            "GET",
            "/visits",
            params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        )

    async def ad_spend(self, date_from: date, date_to: date) -> dict[str, Any]:
        return await self._req(
            "GET",
            "/ad-spend",
            params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        )


def channel_for(conv_channel: str) -> str:
    """Наш канал діалогу → канал запису в MDS."""
    return "instagram" if conv_channel == "instagram" else "telegram-ai"
