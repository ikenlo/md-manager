"""Параметри cookie сесії — для майбутнього входу через cookie (зараз токен у заголовку)."""

from fastapi import Response

from app.config import get_settings

SESSION_COOKIE = "mds_session"


def session_cookie_params() -> dict:
    s = get_settings()
    return {
        "httponly": True,
        "secure": s.is_production,
        "samesite": "lax",
        "max_age": s.session_ttl_days * 86400,
        "path": "/",
    }


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, **session_cookie_params())


def clear_session_cookie(response: Response) -> None:
    p = session_cookie_params()
    response.delete_cookie(
        SESSION_COOKIE, path=p["path"], secure=p["secure"], httponly=True, samesite="lax"
    )
