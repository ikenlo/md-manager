from starlette.datastructures import URL
from starlette.requests import HTTPConnection
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import LOCAL_HOSTS
from app.services.net import client_scheme


class HTTPSRedirectMiddleware:
    """http → https у production з урахуванням X-Forwarded-Proto від тунелю.

    Стандартний Starlette-варіант дивиться лише на url.scheme, а за тунелем вона завжди http —
    це був би нескінченний редирект. Локальні звернення (localhost) не перенаправляємо,
    щоб працювали перевірки з самої машини.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        conn = HTTPConnection(scope)
        host = (conn.url.hostname or "").lower()
        if host in LOCAL_HOSTS or client_scheme(conn) in ("https", "wss"):
            await self.app(scope, receive, send)
            return
        url = URL(scope=scope)
        target = url.replace(scheme="wss" if url.scheme == "ws" else "https", port=None)
        await RedirectResponse(str(target), status_code=308)(scope, receive, send)
