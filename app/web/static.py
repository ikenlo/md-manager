"""Роздача веб-застосунку: / → index.html, /static/* → файли. Стара адреса /panel веде на /."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import __version__

ROOT = Path(__file__).parent / "static"


def index_html() -> str:
    return (ROOT / "index.html").read_text(encoding="utf-8").replace("__V__", __version__)


def mount(app: FastAPI) -> None:
    app.mount("/static", StaticFiles(directory=ROOT), name="static")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> HTMLResponse:
        return HTMLResponse(index_html(), headers={"Cache-Control": "no-cache"})

    @app.get("/panel", include_in_schema=False)
    @app.get("/panel/{rest:path}", include_in_schema=False)
    def old_panel(rest: str = "") -> RedirectResponse:
        return RedirectResponse("/", status_code=301)
