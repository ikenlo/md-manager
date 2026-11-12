"""JSON API для веб-застосунку MDS Manager (/api/...). Сторінки — app/web/static (SPA).

Кожен маршрут перевіряє сесію й право ролі; кожна дія людини пишеться в журнал (app/core/audit.py).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.agent.usage import UsageReport
from app.ai import analyst as an
from app.ai.budget import month_start
from app.ai.jobs import Background
from app.analytics.daily import GROUP_NAMES, DayStats
from app.analytics.dashboard import Dashboard
from app.config import Settings
from app.content.storage import PhotoError
from app.content.studio import CATEGORY_NAMES, MAX_REJECTIONS, Studio
from app.core import approvals
from app.core.audit import audit, recent
from app.db.models import ContentItem, ContentPhoto, PostStat
from app.web import session as sess

MAX_FILES = 30
INVERSE = {"no_show", "spend"}  # зростання — погано
MONEY_ROWS = {("salon", "revenue")}
MONEY_GROUPS = {"meta_ads", "google_ads"}


@dataclass
class Ctx:
    settings: Callable[[], Settings]
    engine: Callable[[], Engine]
    studio: Callable[[], Studio | None] = lambda: None
    jobs: Background = field(default_factory=Background)
    hub: an.Hub = field(default_factory=lambda: an.Hub(None))
    dashboard: Callable[[], Awaitable[Dashboard]] | None = None
    day: Callable[[], Awaitable[DayStats]] | None = None
    mds_http: httpx.AsyncClient | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)


class LoginIn(BaseModel):
    username: str = ""
    password: str
    device_token: str | None = None


class VerifyIn(BaseModel):
    challenge_id: int
    code: str
    remember: bool = False
    device_label: str | None = None


class ItemAction(BaseModel):
    reason: str = ""
    photo_id: int | None = None


class Decide(BaseModel):
    approve: bool
    reason: str = ""


class MonthIn(BaseModel):
    month: str = ""


def _month(v: str | None, today: date) -> date:
    try:
        return datetime.strptime(v or "", "%Y-%m").date()
    except ValueError:
        return today.replace(day=1)


# --- серіалізація ----------------------------------------------------------------


def day_json(day: DayStats, p: sess.Principal) -> dict[str, Any]:
    groups = []
    for g, rows in day.groups():
        if g in MONEY_GROUPS and not p.can("money"):
            continue
        out = [
            {"key": r.key, "label": r.label, "value": r.value, "avg": r.avg, "delta": r.delta,
             "money": r.money, "inverse": r.key in INVERSE}
            for r in rows
            if p.can("money") or (g, r.key) not in MONEY_ROWS
        ]  # fmt: skip
        groups.append({"key": g, "name": GROUP_NAMES[g], "rows": out})
    return {"day": day.day.isoformat(), "groups": groups, "notes": day.notes,
            "followers": day.followers}  # fmt: skip


def item_json(it: ContentItem, jobs: Background) -> dict[str, Any]:
    return {
        "id": it.id, "date": it.slot_date.isoformat(), "kind": it.kind, "status": it.status,
        "topic": it.topic, "caption": it.caption, "hashtags": json.loads(it.hashtags or "[]"),
        "cta": it.cta, "photo_id": it.photo_id, "photo_note": it.photo_note,
        "image": it.image_file, "image_status": it.image_status,
        "rejections": it.rejections, "image_rejections": it.image_rejections,
        "topics_tried": it.topics_tried,
        "busy_text": f"item:{it.id}" in jobs.running,
        "busy_image": f"image:{it.id}" in jobs.running,
        "error": jobs.errors.get(f"item:{it.id}") or jobs.errors.get(f"image:{it.id}") or "",
    }  # fmt: skip


def photo_json(p: ContentPhoto, jobs: Background) -> dict[str, Any]:
    return {"id": p.id, "file": p.file, "description": p.description, "category": p.category,
            "category_name": CATEGORY_NAMES.get(p.category, "Фото"),
            "busy": f"photo:{p.id}" in jobs.running}  # fmt: skip


def build_router(ctx: Ctx) -> APIRouter:
    r = APIRouter(prefix="/api")

    def who(request: Request, perm: str | None = None) -> sess.Principal:
        p = sess.current(request, ctx.settings())
        if perm:
            sess.need(p, perm)
        return p

    def log(actor: str, action: str, target: str = "", details: str = "") -> None:
        with Session(ctx.engine()) as s, s.begin():
            audit(s, actor, action, target, details)

    def today() -> date:
        return ctx.clock().astimezone(ctx.settings().zone).date()

    def studio() -> Studio:
        st = ctx.studio()
        if st is None:
            raise HTTPException(503, "Контент-план ще не готовий — сервер запускається")
        return st

    # --- вхід ------------------------------------------------------------------
    def signed_in(p: sess.Principal, extra: dict[str, Any] | None = None) -> JSONResponse:
        st = ctx.settings()
        resp = JSONResponse({"user": p.public(), **(extra or {})})
        resp.set_cookie(sess.COOKIE, sess.issue(st, p), httponly=True, secure=True,
                        samesite="strict", max_age=st.session_days * 86400)  # fmt: skip
        log(p.label, "auth.login")
        return resp

    async def mds_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
        st = ctx.settings()
        http = ctx.mds_http or httpx.AsyncClient(timeout=15)
        try:
            res = await http.post(st.mds_url.rstrip("/") + path, json=body)
        except httpx.HTTPError as e:
            raise HTTPException(503, "MDS Connect недоступний — спробуйте за хвилину") from e
        data = res.json() if res.content else {}
        if res.status_code >= 400:
            raise HTTPException(401, data.get("detail") or "Невірний логін або пароль")
        return data

    def from_mds(data: dict[str, Any]) -> JSONResponse:
        u = data.get("user") or {}
        role = sess.role_from_mds(u.get("role", ""))
        if role is None:
            raise HTTPException(403, "MDS Manager — для директора й адміністраторів. "
                                     "Майстри працюють у MDS Connect.")  # fmt: skip
        p = sess.Principal(int(u["id"]), u.get("full_name") or u.get("username") or "", role)
        extra = {"device_token": data["device_token"]} if data.get("device_token") else None
        return signed_in(p, extra)

    @r.post("/auth/login")
    async def login(body: LoginIn) -> Response:
        st = ctx.settings()
        if st.mds_url:
            data = await mds_post("/api/auth/login", body.model_dump())
            if data.get("twofa"):
                return JSONResponse({"twofa": True, "challenge_id": data["challenge_id"],
                                     "expires_in": data.get("expires_in", 300)})  # fmt: skip
            return from_mds(data)
        if st.panel_password and body.password == st.panel_password:
            return signed_in(sess.Principal(0, "Власник", "owner"))
        raise HTTPException(401, "Невірний пароль")

    @r.post("/auth/verify")
    async def verify(body: VerifyIn) -> Response:
        if not ctx.settings().mds_url:
            raise HTTPException(400, "Підтвердження кодом не потрібне")
        return from_mds(await mds_post("/api/auth/login/verify", body.model_dump()))

    @r.post("/auth/logout")
    async def logout(request: Request) -> Response:
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(sess.COOKIE)
        return resp

    @r.get("/me")
    async def me(request: Request) -> dict[str, Any]:
        p = who(request)
        out: dict[str, Any] = {"user": p.public(), "mds_url": ctx.settings().mds_url}
        if p.can("approvals"):
            with Session(ctx.engine()) as s:
                out["approvals_pending"] = approvals.pending_count(s)
        return out

    # --- огляд -----------------------------------------------------------------
    @r.get("/overview")
    async def overview(request: Request) -> dict[str, Any]:
        p = who(request, "overview")
        out: dict[str, Any] = {"ai_enabled": ctx.hub.enabled}
        if ctx.day is not None:
            out["day"] = day_json(await ctx.day(), p)
        if p.can("marketing"):
            rep = an.latest(ctx.engine(), "daily")
            out["report"] = (
                {"day": rep.period_start.isoformat(), "model": rep.model, "cost_usd": rep.cost_usd,
                 **rep.data} if rep else None
            )  # fmt: skip
            out["report_running"] = "daily" in ctx.hub.running
            out["report_error"] = ctx.hub.errors.get("daily", "")
        if p.can("money") and ctx.dashboard is not None:
            db = await ctx.dashboard()
            came = sum(a.came for a in db.ads)
            out["period"] = {
                "days": db.days, "from": db.date_from.isoformat(), "to": db.date_to.isoformat(),
                **db.totals, "ad_spend_minor": db.ad_spend_minor,
                "cost_per_visit_minor": db.ad_spend_minor // came if came else None,
                "followers": db.followers, "notes": db.notes,
            }  # fmt: skip
            names = {a.label: a.name for a in db.ads}
            out["ads"] = [
                {"platform": a.platform, "name": a.name, "campaign": a.campaign,
                 "spend_minor": a.spend_minor, "clicks": a.clicks, "conversations": a.conversations,
                 "bookings": a.bookings, "came": a.came,
                 "cost_per_visit_minor": a.cost_per_visit_minor}
                for a in db.ads
            ]  # fmt: skip
            out["sources"] = [
                {"source": names.get(x.source, x.source), "bookings": x.bookings, "came": x.came,
                 "no_show": x.no_show, "revenue_kop": x.revenue_kop}
                for x in db.sources
            ]  # fmt: skip
            out["ai_month"] = {"total": db.ai_month_total, "budget": db.ai_budget,
                               "rows": [{"provider": a, "kind": b, "calls": c, "cost": d}
                                        for a, b, c, d in db.ai_month]}  # fmt: skip
        with Session(ctx.engine()) as s:
            out["posts"] = [
                {"date": x.published_at.date().isoformat(), "format": x.media_type,
                 "caption": x.caption[:90], "permalink": x.permalink, "reach": x.reach,
                 "views": x.views, "likes": x.likes, "saved": x.saved, "shares": x.shares}
                for x in s.scalars(
                    select(PostStat)
                    .where(PostStat.published_at >= ctx.clock() - timedelta(days=30))
                    .order_by(PostStat.reach.desc()).limit(8)
                )
            ]  # fmt: skip
            if p.can("approvals"):
                out["approvals_pending"] = approvals.pending_count(s)
        return out

    @r.post("/overview/report")
    async def run_report(request: Request) -> dict[str, Any]:
        p = who(request, "marketing")
        if not ctx.hub.enabled:
            raise HTTPException(400, "Потрібен ANTHROPIC_API_KEY")
        ctx.hub.start_daily()
        log(p.label, "report.run")
        return {"ok": True}

    # --- контент-план ----------------------------------------------------------
    @r.get("/content")
    async def content(request: Request, month: str = "") -> dict[str, Any]:
        who(request, "content")
        st = studio()
        m = _month(month, today())
        slots = st.slots(m)
        items = st.items(m)
        gen_key = f"month:{m:%Y-%m}"
        return {
            "month": f"{m:%Y-%m}",
            "posts": sum(1 for x in slots if x.kind == "post"),
            "stories": sum(1 for x in slots if x.kind == "story"),
            "post_weekday": st.settings.content_post_weekday,
            "post_time": st.settings.content_post_time,
            "story_time": st.settings.content_story_time,
            "story_every": st.settings.content_story_every_days,
            "missing": len(slots) - len({(i.slot_date, i.kind) for i in items}),
            "max_rejections": MAX_REJECTIONS,
            "can_write": st.can_write, "can_edit_photos": st.can_edit_photos,
            "generating": gen_key in ctx.jobs.running,
            "error": ctx.jobs.errors.get(gen_key, ""),
            "busy": bool(ctx.jobs.running),
            "items": [item_json(i, ctx.jobs) for i in items],
            "photos": [photo_json(x, ctx.jobs) for x in st.photos()],
        }  # fmt: skip

    @r.post("/content/generate")
    async def generate(request: Request, body: MonthIn) -> dict[str, Any]:
        p = who(request, "content")
        st = studio()
        if not st.can_write:
            raise HTTPException(400, "Щоб AI пропонував ідеї, потрібен ANTHROPIC_API_KEY")
        m = _month(body.month, today())
        ctx.jobs.start(f"month:{m:%Y-%m}", lambda: st.generate_month(m))
        log(p.label, "content.generate", f"month:{m:%Y-%m}")
        return {"ok": True}

    @r.post("/content/reset")
    async def reset(request: Request, body: MonthIn) -> dict[str, Any]:
        p = who(request, "content")
        m = _month(body.month, today())
        n = studio().reset_month(m)
        log(p.label, "content.reset", f"month:{m:%Y-%m}", f"видалено ідей: {n}")
        return {"deleted": n}

    @r.post("/content/photos")
    async def upload(
        request: Request,
        files: list[UploadFile] = File(...),  # noqa: B008
        item_id: int | None = Form(None),
    ) -> dict[str, Any]:
        p = who(request, "content")
        st = studio()
        errors, added = [], []
        for up in files[:MAX_FILES]:
            try:
                added.append(st.add_photo(await up.read(), up.filename or ""))
            except PhotoError as e:
                errors.append(f"{up.filename}: {e}")
        if len(files) > MAX_FILES:
            errors.append(f"За раз — до {MAX_FILES} фото, решту надішліть ще раз.")
        if st.can_write:
            for pid in added:
                ctx.jobs.start(f"photo:{pid}", lambda pid=pid: st.describe_photo(pid))
        if item_id and added:
            try:
                st.set_photo(item_id, added[0])
                if st.can_edit_photos and _status(st, item_id) == "approved":
                    ctx.jobs.start(f"image:{item_id}", lambda: st.edit_image(item_id))
            except ValueError as e:
                errors.append(str(e))
        if added:
            target = f"content_item:{item_id}" if item_id else ""
            log(p.label, "content.photos", target, f"фото: {len(added)}")
        return {"added": added, "errors": errors}

    @r.delete("/content/photos/{photo_id}")
    async def delete_photo(request: Request, photo_id: int) -> dict[str, Any]:
        p = who(request, "content")
        try:
            studio().delete_photo(photo_id)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        log(p.label, "content.photo_delete", f"photo:{photo_id}")
        return {"ok": True}

    @r.get("/content/media/{name}")
    async def media(request: Request, name: str, thumb: int = 0, download: int = 0) -> Response:
        who(request, "content")
        st = studio()
        try:
            path = st.media.thumb_path(name) if thumb else st.media.path(name)
        except PhotoError:
            return Response(status_code=404)
        if not path.is_file():
            return Response(status_code=404)
        headers = {"Cache-Control": "private, max-age=86400"}
        if download:
            headers["Content-Disposition"] = f"attachment; filename=md-{name}"
        return FileResponse(path, media_type="image/jpeg", headers=headers)

    def _status(st: Studio, item_id: int) -> str:
        with Session(st.engine) as s:
            it = s.get(ContentItem, item_id)
            return it.status if it else ""

    @r.post("/content/items/{item_id}/{action}")
    async def item_action(
        request: Request, item_id: int, action: str, body: ItemAction | None = None
    ) -> dict[str, Any]:
        p = who(request, "content")
        st = studio()
        body = body or ItemAction()
        if f"item:{item_id}" in ctx.jobs.running or f"image:{item_id}" in ctx.jobs.running:
            raise HTTPException(409, "AI ще працює над цим пунктом — зачекайте хвилину")
        edit = lambda: ctx.jobs.start(f"image:{item_id}", lambda: st.edit_image(item_id))  # noqa: E731
        try:
            if action == "approve":
                if st.approve(item_id) and st.can_edit_photos:
                    edit()
            elif action == "reject":
                if not st.can_write:
                    raise ValueError("Щоб AI переробив ідею, потрібен ANTHROPIC_API_KEY")
                mode = st.reject(item_id, body.reason)
                ctx.jobs.start(f"item:{item_id}", lambda: st.rework(item_id, mode))
            elif action == "photo":
                if body.photo_id is None:
                    raise ValueError("Оберіть фото")
                st.set_photo(item_id, body.photo_id)
                if st.can_edit_photos and _status(st, item_id) == "approved":
                    edit()
            elif action == "image-retry":
                edit()
            elif action == "image-original":
                st.use_original(item_id)
            elif action == "image-approve":
                st.approve_image(item_id)
            elif action == "image-reject":
                if st.reject_image(item_id, body.reason) == "retry" and st.can_edit_photos:
                    edit()
            elif action == "published":
                st.mark_published(item_id)
            else:
                raise HTTPException(404, "Невідома дія")
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        log(p.label, f"content.{action}", f"content_item:{item_id}", body.reason[:200])
        return {"ok": True}

    # --- погодження, журнал, налаштування -----------------------------------------
    @r.get("/approvals")
    async def approvals_list(request: Request, status: str = "pending") -> list[dict[str, Any]]:
        who(request, "approvals")
        with Session(ctx.engine()) as s:
            return approvals.listing(s, status or None)

    @r.post("/approvals/{approval_id}")
    async def approvals_decide(request: Request, approval_id: int, body: Decide) -> dict[str, Any]:
        p = who(request, "approvals")
        try:
            with Session(ctx.engine()) as s, s.begin():
                a = approvals.decide(s, approval_id, body.approve, p.label, body.reason)
                status = a.status
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return {"status": status}

    @r.get("/audit")
    async def audit_list(request: Request, limit: int = 100) -> list[dict[str, Any]]:
        who(request, "audit")
        with Session(ctx.engine()) as s:
            return recent(s, min(max(limit, 1), 500))

    @r.get("/settings")
    async def settings_view(request: Request) -> dict[str, Any]:
        who(request, "settings")
        st = ctx.settings()
        with Session(ctx.engine()) as s:
            spent = UsageReport.cost_since(s, month_start(ctx.clock(), st.zone))
        conn = [
            ("MDS Connect", "Записи, клієнти, каталог, виручка", bool(st.mds_url and st.mds_token)),
            ("Instagram Direct", "Повідомлення клієнтів", bool(st.ig_app_secret)),
            ("Telegram-бот", "Клієнтський бот і сповіщення", bool(st.tg_bot_token)),
            ("Meta: статистика й реклама", "Instagram, Facebook, Meta Ads", bool(st.meta_token)),
            ("Google Ads", "Витрати й конверсії кампаній", st.google_ads_enabled),
            ("Claude", "Діалоги, ідеї, аналітика", bool(st.anthropic_api_key)),
            ("Gemini", "Обробка фото", bool(st.gemini_api_key)),
        ]
        return {
            "connections": [{"name": a, "what": b, "ok": c} for a, b, c in conn],
            "ai_budget": st.ai_monthly_budget_usd, "ai_spent": round(spent, 2),
            "content": {"post_weekday": st.content_post_weekday,
                        "story_every": st.content_story_every_days,
                        "auto_day": st.content_plan_auto_day},
            "analyst_daily": st.analyst_daily,
        }  # fmt: skip

    return r
