"""Справжні IP і схема клієнта за Cloudflare Tunnel.

cloudflared звертається до uvicorn з 127.0.0.1 по http, тож request.client і url.scheme
описують тунель, а не відвідувача. Заголовкам Cloudflare віримо лише від довірених проксі,
інакше будь-хто підставив би свій IP і обійшов ліміт входу.
"""

from starlette.requests import HTTPConnection

from app.config import get_settings


def _from_trusted_proxy(conn: HTTPConnection) -> bool:
    peer = conn.client.host if conn.client else None
    return peer is not None and peer in get_settings().trusted_proxy_list


def client_ip(conn: HTTPConnection) -> str:
    peer = conn.client.host if conn.client else "unknown"
    if _from_trusted_proxy(conn):
        forwarded = conn.headers.get("cf-connecting-ip") or conn.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return peer


def client_scheme(conn: HTTPConnection) -> str:
    if _from_trusted_proxy(conn):
        proto = conn.headers.get("x-forwarded-proto")
        if proto:
            return proto.split(",")[0].strip().lower()
    return conn.url.scheme
