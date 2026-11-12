import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes import auth, dialogues, settings
from app.config import FRONTEND_DIST, get_settings
from app.security import HTTPSRedirectMiddleware
from app.services.rate_limit import limiter, rate_limit_handler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mds")


def create_app() -> FastAPI:
    cfg = get_settings()
    app = FastAPI(
        title="MDs Manager",
        version="0.1.0",
        # Публічно (через тунель) схему API не показуємо
        docs_url=None if cfg.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if cfg.is_production else "/openapi.json",
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

    # Останній доданий — зовнішній: TrustedHost → HTTPS → CORS → застосунок
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if cfg.is_production:
        app.add_middleware(HTTPSRedirectMiddleware)
        if not cfg.allowed_hosts.strip():
            log.warning("APP_ENV=production, але ALLOWED_HOSTS порожній — домен тунелю отримає 400")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=cfg.allowed_host_list)

    app.include_router(auth.router)
    app.include_router(dialogues.router)
    app.include_router(settings.router)

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Зібраний frontend (npm run build) — з того ж origin, що й API."""
    dist = Path(FRONTEND_DIST)
    index = dist / "index.html"
    if not index.is_file():
        return
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "Не знайдено")
        file = (dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(dist.resolve()):
            return FileResponse(file)
        return FileResponse(index)


app = create_app()
