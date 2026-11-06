"""Сесії й права MDS Manager.

Вхід — логіном MDS Connect (сервер перевіряє пароль у MDS і бере звідти роль). Ролі MDS → права тут:
директор бачить усе; адміністратор — огляд без грошей, діалоги й контент; майстрам доступу немає.
Без MDS_URL (локально, тести) — вхід паролем PANEL_PASSWORD як власник.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.config import Settings

COOKIE = "mdsm_session"
ROLE_NAMES = {"owner": "Директор", "admin": "Адміністратор"}
PERMS = {
    "owner": {"overview", "money", "marketing", "content", "dialogs", "approvals", "audit",
              "settings"},
    "admin": {"overview", "content", "dialogs"},
}  # fmt: skip
_fallback_secret = secrets.token_hex(32)


@dataclass(frozen=True)
class Principal:
    user_id: int
    name: str
    role: str  # owner | admin

    @property
    def perms(self) -> set[str]:
        return PERMS.get(self.role, set())

    def can(self, perm: str) -> bool:
        return perm in self.perms

    @property
    def label(self) -> str:
        """Як підписуємо дії в журналі."""
        return f"{self.name} ({ROLE_NAMES.get(self.role, self.role).lower()})"

    def public(self) -> dict:
        return {
            "id": self.user_id,
            "name": self.name,
            "role": self.role,
            "role_name": ROLE_NAMES.get(self.role, self.role),
            "perms": sorted(self.perms),
        }


def role_from_mds(mds_role: str) -> str | None:
    return {"director": "owner", "admin": "admin"}.get(mds_role)


def _secret(settings: Settings) -> bytes:
    return (settings.session_secret or _fallback_secret).encode()


def issue(settings: Settings, p: Principal) -> str:
    body = {"u": p.user_id, "n": p.name, "r": p.role,
            "e": int(time.time()) + settings.session_days * 86400}  # fmt: skip
    raw = base64.urlsafe_b64encode(json.dumps(body, ensure_ascii=False).encode()).decode()
    sig = hmac.new(_secret(settings), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def read(settings: Settings, token: str) -> Principal | None:
    raw, _, sig = token.partition(".")
    good = hmac.new(_secret(settings), raw.encode(), hashlib.sha256).hexdigest()
    if not raw or not hmac.compare_digest(sig, good):
        return None
    try:
        body = json.loads(base64.urlsafe_b64decode(raw.encode()))
    except ValueError:
        return None
    if body.get("e", 0) < time.time() or body.get("r") not in PERMS:
        return None
    return Principal(int(body["u"]), str(body["n"]), str(body["r"]))


def current(request: Request, settings: Settings) -> Principal:
    p = read(settings, request.cookies.get(COOKIE, ""))
    if p is None:
        raise HTTPException(401, "Увійдіть ще раз")
    return p


def need(p: Principal, perm: str) -> None:
    if not p.can(perm):
        raise HTTPException(403, "Недостатньо прав")
