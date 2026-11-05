"""Панель власника /panel: одна сторінка з записами за джерелами, рекламою, Instagram і витратами AI.

Вхід за паролем PANEL_PASSWORD (cookie з HMAC). Без пароля в налаштуваннях панель вимкнена (404).
HTML рендериться на сервері, без зовнішніх скриптів; усі дані екрануються.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Awaitable, Callable
from datetime import date
from html import escape

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.analytics.dashboard import Dashboard
from app.config import Settings

COOKIE = "mds_panel"
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]

CSS = """
:root{--bg:#eef1ec;--surface:#f8faf6;--ink:#12261d;--muted:#5a6b61;--line:#d3dbd3;--green:#163a2b;
--gold:#9a7428;--tint:#e4ebe3;--good:#1f7a4d;--warn:#a5561c;--s1:#163a2b;--s2:#c08a2d;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0c1a14;--surface:#12241b;--ink:#ece6d6;--muted:#9fb0a5;
--line:#23392e;--green:#c9a458;--gold:#d2ad62;--tint:#172d23;--good:#5cc18d;--warn:#e39a5e;--s1:#7fc4a2;
--s2:#d2ad62;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 "Segoe UI",system-ui,-apple-system,sans-serif;padding:24px max(16px,env(safe-area-inset-left))}
.wrap{max-width:1040px;margin:0 auto;display:grid;gap:22px}
h1{font:600 30px/1.1 Georgia,serif;margin:0}h2{font:600 20px/1.2 Georgia,serif;margin:0 0 10px}
.mark{font:600 11px/1 Georgia,serif;letter-spacing:.3em;text-transform:uppercase;color:var(--gold)}
.sub{color:var(--muted);margin:4px 0 0;font-size:14px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px}
.kpi b{display:block;font:600 26px/1.1 Georgia,serif;font-variant-numeric:tabular-nums}
.kpi span{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
section{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px;min-width:0}
.tw{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-size:12px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.05em}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.good{color:var(--good);font-weight:600}.warn{color:var(--warn);font-weight:600}
.note{background:var(--tint);border-radius:8px;padding:9px 12px;font-size:13px;color:var(--muted);margin:0}
.legend{display:flex;gap:16px;font-size:13px;color:var(--muted)}.legend i{display:inline-block;width:12px;
height:3px;vertical-align:middle;margin-right:6px}
.grid2{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:22px}
@media (max-width:800px){.grid2{grid-template-columns:minmax(0,1fr)}}
form{display:flex;gap:8px;flex-wrap:wrap}input{font:inherit;padding:9px 12px;border-radius:8px;
border:1px solid var(--line);background:var(--bg);color:var(--ink)}button{font:inherit;font-weight:600;
padding:9px 16px;border-radius:8px;border:0;background:var(--green);color:var(--bg);cursor:pointer}
"""


def _token(settings: Settings) -> str:
    return hmac.new(settings.panel_password.encode(), b"mds-panel-v1", hashlib.sha256).hexdigest()


def _authed(request: Request, settings: Settings) -> bool:
    got = request.cookies.get(COOKIE, "")
    return bool(settings.panel_password) and hmac.compare_digest(got, _token(settings))


def _uah(minor: int) -> str:
    return f"{minor // 100:,}".replace(",", " ") + " грн"


def _day(d: date) -> str:
    return f"{WD[d.weekday()]} {d:%d.%m}"


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='uk'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<meta name='robots' content='noindex'><title>{escape(title)}</title>"
        f"<style>{CSS}</style></head><body><div class='wrap'>{body}</div></body></html>"
    )


def login_page(error: str = "") -> str:
    err = f"<p class='note'>{escape(error)}</p>" if error else ""
    return _page(
        "Панель M&D",
        "<div><div class='mark'>M&amp;D · Beauty Salon</div><h1>Панель власника</h1></div>"
        f"{err}<form method='post' action='/panel/login'>"
        "<input type='password' name='password' placeholder='Пароль' autocomplete='current-password' "
        "required aria-label='Пароль'><button type='submit'>Увійти</button></form>",
    )


def _line_chart(series: dict[str, list[tuple[date, float]]]) -> str:
    keys = [k for k in ("reach", "views") if series.get(k)]
    if not keys:
        return "<p class='note'>Даних Instagram ще немає.</p>"
    days = sorted({d for k in keys for d, _ in series[k]})
    top = max(v for k in keys for _, v in series[k]) or 1
    w, h, pl, pr, pt, pb = 640, 220, 48, 16, 12, 28
    X = lambda d: pl + (days.index(d) / max(len(days) - 1, 1)) * (w - pl - pr)  # noqa: E731
    Y = lambda v: pt + (1 - v / top) * (h - pt - pb)  # noqa: E731
    colors = {"reach": "var(--s1)", "views": "var(--s2)"}
    names = {"reach": "Охоплення", "views": "Перегляди"}
    grid = ""
    for i in range(5):
        v = top * i / 4
        grid += (
            f"<line x1='{pl}' x2='{w - pr}' y1='{Y(v):.1f}' y2='{Y(v):.1f}' stroke='var(--line)'/>"
            f"<text x='{pl - 6}' y='{Y(v) + 4:.1f}' text-anchor='end' font-size='11' "
            f"fill='var(--muted)'>{int(v):,}</text>".replace(",", " ")
        )
    step = max(1, len(days) // 6)
    for d in days[::step]:
        grid += (
            f"<text x='{X(d):.1f}' y='{h - 8}' text-anchor='middle' font-size='11' "
            f"fill='var(--muted)'>{d:%d.%m}</text>"
        )
    lines = ""
    for k in keys:
        pts = " ".join(f"{X(d):.1f},{Y(v):.1f}" for d, v in series[k])
        last_d, last_v = series[k][-1]
        lines += (
            f"<polyline points='{pts}' fill='none' stroke='{colors[k]}' stroke-width='2'/>"
            f"<circle cx='{X(last_d):.1f}' cy='{Y(last_v):.1f}' r='3.5' fill='{colors[k]}'/>"
        )
    legend = "".join(f"<span><i style='background:{colors[k]}'></i>{names[k]}</span>" for k in keys)
    return (
        f"<div class='legend'>{legend}</div><svg viewBox='0 0 {w} {h}' width='100%' role='img' "
        f"aria-label='Охоплення й перегляди Instagram по днях'>{grid}{lines}</svg>"
    )


def render(db: Dashboard, salon: str = "M&D") -> str:
    t = db.totals
    show = f"{t['came'] / t['bookings']:.0%}" if t["bookings"] else "—"
    cpv = (
        _uah(db.ad_spend_minor // max(sum(a.came for a in db.ads), 1))
        if db.ad_spend_minor and any(a.came for a in db.ads)
        else "—"
    )
    kpis = [
        ("Записів", f"{t['bookings']}"),
        ("Прийшли", f"{t['came']} · {show}"),
        ("Виручка", _uah(t["revenue_kop"])),
        ("Реклама", _uah(db.ad_spend_minor)),
        ("Реклама на візит", cpv),
        ("Підписники", f"{db.followers:,}".replace(",", " ") if db.followers is not None else "—"),
    ]
    kpi_html = "".join(
        f"<div class='kpi'><span>{escape(k)}</span><b>{escape(v)}</b></div>" for k, v in kpis
    )

    src_rows = (
        "".join(
            f"<tr><td>{escape(r.source)}</td><td class='n'>{r.bookings}</td><td class='n'>{r.came}</td>"
            f"<td class='n'>{r.no_show or ''}</td><td class='n'>{_uah(r.revenue_kop) if r.revenue_kop else ''}</td></tr>"
            for r in db.sources
        )
        or "<tr><td colspan='5'>Записів за період немає</td></tr>"
    )

    ad_rows = ""
    for a in db.ads:
        cpv_a = a.cost_per_visit_minor
        cls = (
            "good"
            if cpv_a is not None and cpv_a <= 25000
            else ("warn" if a.spend_minor and not a.came else "")
        )
        ad_rows += (
            f"<tr><td>{escape(a.name)}<br><small style='color:var(--muted)'>{escape(a.campaign)}</small></td>"
            f"<td class='n'>{_uah(a.spend_minor)}</td><td class='n'>{a.clicks}</td>"
            f"<td class='n'>{a.conversations}</td><td class='n'>{a.bookings}</td><td class='n'>{a.came}</td>"
            f"<td class='n {cls}'>{_uah(cpv_a) if cpv_a is not None else 'немає візитів'}</td></tr>"
        )
    ad_rows = ad_rows or "<tr><td colspan='7'>Даних реклами ще немає</td></tr>"

    ai_rows = (
        "".join(
            f"<tr><td>{escape(p)} / {escape(k)}</td><td class='n'>{n}</td><td class='n'>${c:.2f}</td></tr>"
            for p, k, n, c in db.ai_month
        )
        or "<tr><td colspan='3'>Витрат ще немає</td></tr>"
    )
    budget = f" з ${db.ai_budget:.0f}" if db.ai_budget > 0 else ""
    notes = "".join(f"<p class='note'>{escape(n)}</p>" for n in db.notes)

    body = (
        f"<div><div class='mark'>{escape(salon)} · Beauty Salon</div><h1>Панель власника</h1>"
        f"<p class='sub'>{db.days} днів: {_day(db.date_from)} — {_day(db.date_to)}</p></div>{notes}"
        f"<div class='kpis'>{kpi_html}</div>"
        "<section><h2>Реклама: що окупається</h2><div class='tw'><table><thead><tr><th>Оголошення</th>"
        "<th class='n'>Витрати</th><th class='n'>Кліки</th><th class='n'>Діалоги</th><th class='n'>Записи</th>"
        "<th class='n'>Прийшли</th><th class='n'>Ціна візиту</th></tr></thead>"
        f"<tbody>{ad_rows}</tbody></table></div></section>"
        "<div class='grid2'><section><h2>Instagram по днях</h2>"
        f"{_line_chart(db.ig_series)}</section>"
        "<section><h2>Звідки записи</h2><div class='tw'><table><thead><tr><th>Джерело</th>"
        "<th class='n'>Записи</th><th class='n'>Прийшли</th><th class='n'>Неявки</th><th class='n'>Виручка</th>"
        f"</tr></thead><tbody>{src_rows}</tbody></table></div></section></div>"
        f"<section><h2>AI цього місяця: ${db.ai_month_total:.2f}{budget}</h2><div class='tw'><table>"
        "<thead><tr><th>Модель / вид</th><th class='n'>Викликів</th><th class='n'>Вартість</th></tr></thead>"
        f"<tbody>{ai_rows}</tbody></table></div></section>"
    )
    return _page("Панель M&D", body)


def build_router(
    get_settings: Callable[[], Settings], get_dashboard: Callable[[], Awaitable[Dashboard]]
) -> APIRouter:
    router = APIRouter()

    @router.get("/panel", response_class=HTMLResponse)
    async def panel(request: Request) -> Response:
        settings = get_settings()
        if not settings.panel_password:
            return Response(status_code=404)
        if not _authed(request, settings):
            return HTMLResponse(login_page())
        return HTMLResponse(render(await get_dashboard()))

    @router.post("/panel/login")
    async def login(password: str = Form("")) -> Response:
        settings = get_settings()
        if not settings.panel_password:
            return Response(status_code=404)
        if not hmac.compare_digest(password, settings.panel_password):
            return HTMLResponse(login_page("Невірний пароль"), status_code=401)
        resp = RedirectResponse("/panel", status_code=303)
        resp.set_cookie(COOKIE, _token(settings), httponly=True, secure=True, samesite="strict",
                        max_age=30 * 86400)  # fmt: skip
        return resp

    return router
