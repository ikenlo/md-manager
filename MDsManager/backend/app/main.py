import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes import _test, auth, dialogues, media, settings, ws
from app.config import FRONTEND_DIST, get_settings
from app.security import HTTPSRedirectMiddleware
from app.services.events import events
from app.services.outbound_worker import OutboundWorker
from app.services.rate_limit import limiter, rate_limit_handler
from app.services.ws_manager import forward_to_ws

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mds")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cfg = get_settings()
    # події воркера й API → усі відкриті вкладки
    unsubscribe = events.subscribe(forward_to_ws)
    scheduler: AsyncIOScheduler | None = None
    if cfg.outbound_worker_enabled:
        worker = OutboundWorker()
        scheduler = AsyncIOScheduler(timezone="UTC")
        # max_instances=1 + coalesce: прогони не накладаються і не накопичуються
        scheduler.add_job(
            worker.process_once,
            "interval",
            seconds=cfg.outbound_interval_seconds,
            id="outbound_worker",
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        log.info(
            "Outbound worker started (interval: %d sec, mock_meta: %s)",
            cfg.outbound_interval_seconds,
            cfg.mock_meta,
        )
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        unsubscribe()
        if scheduler is not None:
            scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    cfg = get_settings()
    app = FastAPI(
        lifespan=lifespan,
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
    app.include_router(media.router)
    app.include_router(ws.router)
    if cfg.mock_meta and not cfg.is_production:
        app.include_router(_test.router)

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
