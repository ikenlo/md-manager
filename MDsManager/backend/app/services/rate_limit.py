from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.services.net import client_ip


def _key(request: Request) -> str:
    # slowapi передає запит лише в параметр з назвою саме `request`
    return client_ip(request)


# Пам'ять процесу: застосунок працює однією реплікою
limiter = Limiter(key_func=_key)


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Забагато спроб входу. Спробуйте пізніше."},
        headers={"Retry-After": str(exc.limit.limit.get_expiry())},
    )
