"""Панель власника /panel: статистика дня, AI-аналітик, записи за джерелами, реклама, пости, AI.
/panel/content — контент-план на місяць для Instagram і Facebook з промптами для картинок і відео.

Вхід за паролем PANEL_PASSWORD (cookie з HMAC). Без пароля в налаштуваннях панель вимкнена (404).
HTML рендериться на сервері, без зовнішніх скриптів; усі дані екрануються.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from html import escape
from typing import Any

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.ai import analyst as an
from app.analytics.daily import GROUP_NAMES, DayStats
from app.analytics.dashboard import Dashboard
from app.config import Settings
from app.db.models import PostStat

COOKIE = "mds_panel"
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]

CSS = """
:root{--bg:#eef1ec;--surface:#f8faf6;--ink:#12261d;--muted:#5a6b61;--line:#d3dbd3;--green:#163a2b;
--gold:#9a7428;--tint:#e4ebe3;--good:#1f7a4d;--warn:#a5561c;--s1:#163a2b;--s2:#c08a2d;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0c1a14;--surface:#12241b;--ink:#ece6d6;--muted:#9fb0a5;
--line:#23392e;--green:#c9a458;--gold:#d2ad62;--tint:#172d23;--good:#5cc18d;--warn:#e39a5e;--s1:#7fc4a2;
--s2:#d2ad62;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0c1a14;--surface:#12241b;--ink:#ece6d6;--muted:#9fb0a5;
--line:#23392e;--green:#c9a458;--gold:#d2ad62;--tint:#172d23;--good:#5cc18d;--warn:#e39a5e;--s1:#7fc4a2;
--s2:#d2ad62;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 "Segoe UI",system-ui,-apple-system,sans-serif;padding:24px max(16px,env(safe-area-inset-left))}
.wrap{max-width:1040px;margin:0 auto;display:grid;gap:22px}
h1{font:600 30px/1.1 Georgia,serif;margin:0}h2{font:600 20px/1.2 Georgia,serif;margin:0 0 10px}
.mark{font:600 11px/1 Georgia,serif;letter-spacing:.3em;text-transform:uppercase;color:var(--gold)}
.sub{color:var(--muted);margin:4px 0 0;font-size:14px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
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
.grid2{display:grid;grid-template-columns:minmax(0,1fr);gap:22px}
.nav{display:flex;gap:14px;flex-wrap:wrap;font-size:14px}.nav a,a{color:var(--gold)}
.list{margin:0;padding-left:20px;display:grid;gap:6px}.list li.good{font-weight:400}
.tag{display:inline-block;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;
padding:2px 8px;border-radius:99px;background:var(--tint);color:var(--muted);margin-right:6px}
.tag.high{background:var(--warn);color:var(--bg)}.cards{display:grid;gap:12px}
.card{border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:var(--bg);min-width:0}
.card h3{font:600 16px/1.3 Georgia,serif;margin:6px 0}.card p{margin:6px 0}
.muted{color:var(--muted);font-size:13px}pre{white-space:pre-wrap;word-break:break-word;margin:6px 0;
font:13px/1.45 ui-monospace,Consolas,monospace;background:var(--surface);border:1px solid var(--line);
border-radius:8px;padding:8px 10px}details summary{cursor:pointer;color:var(--gold);font-size:14px}
.cap{white-space:pre-wrap}.copy{font-size:12px;padding:4px 10px;background:var(--tint);color:var(--ink)}
.head{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap}
table.fix{table-layout:fixed}table.fix th:first-child{width:46%}table.fix td{white-space:normal}
td.up{color:var(--good)}td.down{color:var(--warn)}
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


COPY_JS = (
    "document.addEventListener('click',e=>{const b=e.target.closest('[data-copy]');if(!b)return;"
    "const t=document.getElementById(b.dataset.copy);if(!t)return;"
    "navigator.clipboard.writeText(t.textContent).then(()=>{b.textContent='Скопійовано'})});"
)


def _page(title: str, body: str, *, refresh: bool = False) -> str:
    meta = "<meta http-equiv='refresh' content='20'>" if refresh else ""
    return (
        "<!doctype html><html lang='uk'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<meta name='robots' content='noindex'>{meta}<title>{escape(title)}</title>"
        f"<style>{CSS}</style></head><body><div class='wrap'>{body}</div>"
        f"<script>{COPY_JS}</script></body></html>"
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


@dataclass
class Extras:
    """Додаткові блоки головної сторінки: день, AI-аналітик, пости."""

    day: DayStats | None = None
    report: an.Report | None = None
    posts: list[PostStat] = field(default_factory=list)
    ai_enabled: bool = False
    running: bool = False
    error: str = ""


INVERSE = {"no_show", "spend"}  # зростання — погано


def _num(v: float | None, money: bool) -> str:
    if v is None:
        return "—"
    if money:
        return _uah(int(v))
    return f"{v:,.0f}".replace(",", " ") if abs(v) >= 10 or v == int(v) else f"{v:.1f}"


def _day_section(day: DayStats) -> str:
    if not day.rows:
        return (
            f"<section id='day'><h2>Вчора, {_day(day.day)}</h2>"
            "<p class='note'>Даних за день ще немає — підключіть MDS Connect, Meta чи Google Ads."
            "</p></section>"
        )
    parts = []
    for group, rows in day.groups():
        trs = ""
        for r in rows:
            d = r.delta
            if d is None or abs(d) < 0.005:
                cell = "<td class='n'>—</td>"
            else:
                good = (d > 0) != (r.key in INVERSE)
                cell = f"<td class='n {'up' if good else 'down'}'>{d:+.0%}</td>"
            trs += (
                f"<tr><td>{escape(r.label)}</td><td class='n'>{_num(r.value, r.money)}</td>"
                f"<td class='n'>{_num(r.avg, r.money)}</td>{cell}</tr>"
            )
        parts.append(
            f"<div class='tw'><table class='fix'><thead><tr><th>{escape(GROUP_NAMES[group])}</th>"
            "<th class='n'>Вчора</th><th class='n'>Сер. 7 дн</th><th class='n'>Зміна</th>"
            f"</tr></thead><tbody>{trs}</tbody></table></div>"
        )
    notes = "".join(f"<p class='note'>{escape(n)}</p>" for n in day.notes)
    return (
        f"<section id='day'><h2>Вчора, {_day(day.day)}</h2>{notes}"
        f"<div class='cards'>{''.join(parts)}</div></section>"
    )


def _copy_block(uid: str, label: str, text: str) -> str:
    if not text:
        return ""
    return (
        f"<div class='head'><span class='muted'>{escape(label)}</span>"
        f"<button type='button' class='copy' data-copy='{uid}'>Копіювати</button></div>"
        f"<pre id='{uid}'>{escape(text)}</pre>"
    )


PRIORITY = {"high": "терміново", "medium": "цього тижня", "low": "за нагоди"}
PLATFORMS = {"instagram": "Instagram", "facebook": "Facebook", "both": "Instagram + Facebook"}


def _ai_section(x: Extras) -> str:
    head = "<div class='head'><h2>AI-аналітик</h2>"
    if x.ai_enabled:
        label = "Готується…" if x.running else "Оновити аналіз"
        dis = " disabled" if x.running else ""
        head += (
            "<form method='post' action='/panel/ai/daily'>"
            f"<button type='submit'{dis}>{label}</button></form>"
        )
    head += "</div>"
    if not x.ai_enabled:
        return (
            f"<section id='ai'>{head}<p class='note'>Потрібен ANTHROPIC_API_KEY — тоді щоранку "
            "тут зʼявиться розбір дня з порадами й ідеями реклами.</p></section>"
        )
    body = ""
    if x.error:
        body += f"<p class='note'>⚠️ {escape(x.error)}</p>"
    if x.running:
        body += "<p class='note'>Аналіз готується, сторінка оновиться сама.</p>"
    r = x.report
    if r is None:
        return f"<section id='ai'>{head}{body}<p class='note'>Звітів ще немає.</p></section>"
    d = r.data
    body += (
        f"<p class='muted'>Звіт за {_day(r.period_start)} · {escape(r.model)} · "
        f"${r.cost_usd:.2f}</p><p>{escape(d.get('summary', ''))}</p>"
    )
    hl = "".join(
        f"<li class='{'good' if h.get('tone') == 'good' else ''}'>"
        f"{'✅' if h.get('tone') == 'good' else '⚠️' if h.get('tone') == 'warn' else '•'} "
        f"{escape(h.get('text', ''))}</li>"
        for h in d.get("highlights") or []
    )
    if hl:
        body += f"<h3>Що видно з цифр</h3><ul class='list'>{hl}</ul>"
    acts = "".join(
        f"<div class='card'><span class='tag {escape(a.get('priority', ''))}'>"
        f"{escape(PRIORITY.get(a.get('priority', ''), ''))}</span>"
        f"<h3>{escape(a.get('title', ''))}</h3><p class='muted'>{escape(a.get('why', ''))}</p>"
        f"<p>{escape(a.get('how', ''))}</p></div>"
        for a in d.get("actions") or []
    )
    if acts:
        body += f"<h3>Що зробити</h3><div class='cards'>{acts}</div>"
    ideas = ""
    for i, a in enumerate(d.get("ad_ideas") or []):
        uid = f"ad{r.id}_{i}"
        ad_text = f"{a.get('headline', '')}\n\n{a.get('primary_text', '')}\n\n{a.get('cta', '')}"
        ideas += (
            f"<div class='card'><span class='tag'>{escape(PLATFORMS.get(a.get('platform'), ''))}"
            f"</span><span class='tag'>{escape(a.get('service', ''))}</span>"
            f"<h3>{escape(a.get('headline', ''))}</h3>"
            f"<p class='muted'>Мета: {escape(a.get('objective', ''))} · Аудиторія: "
            f"{escape(a.get('audience', ''))} · Бюджет: {escape(a.get('budget_hint', ''))}</p>"
            + _copy_block(uid + "t", "Текст оголошення", ad_text)
            + "<details><summary>Промпти для картинки й відео</summary>"
            + _copy_block(uid + "i", "Зображення", a.get("image_prompt", ""))
            + _copy_block(uid + "v", "Відео", a.get("video_prompt", ""))
            + "</details></div>"
        )
    if ideas:
        body += f"<h3>Ідеї нових рекламних постів</h3><div class='cards'>{ideas}</div>"
    return f"<section id='ai'>{head}{body}</section>"


def _safe_url(u: str) -> str:
    return u if u.startswith("https://") else ""


def _posts_section(posts: list[PostStat]) -> str:
    if not posts:
        return ""
    rows = ""
    for p in posts:
        url = _safe_url(p.permalink)
        cap = escape(p.caption[:70] + ("…" if len(p.caption) > 70 else "")) or "без підпису"
        cap = f"<a href='{escape(url)}' rel='noopener' target='_blank'>{cap}</a>" if url else cap
        rows += (
            f"<tr><td>{p.published_at:%d.%m}</td><td>{escape(p.media_type.lower())}</td>"
            f"<td style='white-space:normal;min-width:180px'>{cap}</td>"
            f"<td class='n'>{p.reach}</td><td class='n'>{p.views}</td><td class='n'>{p.likes}</td>"
            f"<td class='n'>{p.saved}</td><td class='n'>{p.shares}</td></tr>"
        )
    return (
        "<section><h2>Пости за 30 днів: що заходить</h2><div class='tw'><table><thead><tr>"
        "<th>Дата</th><th>Формат</th><th>Пост</th><th class='n'>Охоплення</th>"
        "<th class='n'>Перегляди</th><th class='n'>Лайки</th><th class='n'>Збереж.</th>"
        f"<th class='n'>Поширення</th></tr></thead><tbody>{rows}</tbody></table></div></section>"
    )


NAV = (
    "<nav class='nav'><a href='/panel'>Огляд</a><a href='/panel#ai'>AI-аналітик</a>"
    "<a href='/panel/content'>Контент-план</a></nav>"
)


def render(db: Dashboard, salon: str = "M&D", extras: Extras | None = None) -> str:
    x = extras or Extras()
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

    ad_names = {a.label: a.name for a in db.ads}
    src_rows = (
        "".join(
            f"<tr><td>{escape(ad_names.get(r.source, r.source))}</td><td class='n'>{r.bookings}</td><td class='n'>{r.came}</td>"
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
        f"<p class='sub'>{db.days} днів: {_day(db.date_from)} — {_day(db.date_to)}</p></div>{NAV}"
        f"{notes}"
        + (_day_section(x.day) if x.day else "")
        + _ai_section(x)
        + f"<h2 style='margin:8px 0 -8px'>За {db.days} днів</h2><div class='kpis'>{kpi_html}</div>"
        "<section><h2>Реклама: що окупається</h2><div class='tw'><table><thead><tr><th>Оголошення</th>"
        "<th class='n'>Витрати</th><th class='n'>Кліки</th><th class='n'>Діалоги</th><th class='n'>Записи</th>"
        "<th class='n'>Прийшли</th><th class='n'>Ціна візиту</th></tr></thead>"
        f"<tbody>{ad_rows}</tbody></table></div></section>"
        "<div class='grid2'><section><h2>Instagram по днях</h2>"
        f"{_line_chart(db.ig_series)}</section>"
        + _posts_section(x.posts)
        + "<section><h2>Звідки записи</h2><div class='tw'><table><thead><tr><th>Джерело</th>"
        "<th class='n'>Записи</th><th class='n'>Прийшли</th><th class='n'>Неявки</th><th class='n'>Виручка</th>"
        f"</tr></thead><tbody>{src_rows}</tbody></table></div></section></div>"
        f"<section><h2>AI цього місяця: ${db.ai_month_total:.2f}{budget}</h2><div class='tw'><table>"
        "<thead><tr><th>Модель / вид</th><th class='n'>Викликів</th><th class='n'>Вартість</th></tr></thead>"
        f"<tbody>{ai_rows}</tbody></table></div></section>"
    )
    return _page("Панель M&D", body, refresh=x.running)


def _month_name(m: date) -> str:
    names = ["січень", "лютий", "березень", "квітень", "травень", "червень", "липень",
             "серпень", "вересень", "жовтень", "листопад", "грудень"]  # fmt: skip
    return f"{names[m.month - 1]} {m.year}"


def render_content(
    month: date,
    report: an.Report | None,
    *,
    ai_enabled: bool,
    running: bool = False,
    error: str = "",
    salon: str = "M&D",
) -> str:
    prev_m = (month - timedelta(days=1)).replace(day=1)
    next_m = an.next_month(month)
    nav_m = (
        f"<nav class='nav'><a href='/panel/content?m={prev_m:%Y-%m}'>← {_month_name(prev_m)}</a>"
        f"<a href='/panel/content?m={next_m:%Y-%m}'>{_month_name(next_m)} →</a></nav>"
    )
    form = ""
    if ai_enabled:
        label = (
            "Готується…" if running else ("Згенерувати заново" if report else "Згенерувати план")
        )
        dis = " disabled" if running else ""
        form = (
            "<form method='post' action='/panel/content/generate'>"
            f"<input type='hidden' name='month' value='{month:%Y-%m}'>"
            f"<button type='submit'{dis}>{label}</button></form>"
        )
    body = (
        f"<div><div class='mark'>{escape(salon)} · Beauty Salon</div><h1>Контент-план</h1>"
        f"<p class='sub'>Instagram і Facebook · {_month_name(month)}</p></div>{NAV}"
        f"<div class='head'>{nav_m}{form}</div>"
    )
    if not ai_enabled:
        body += "<p class='note'>Потрібен ANTHROPIC_API_KEY, щоб генерувати план.</p>"
    if error:
        body += f"<p class='note'>⚠️ {escape(error)}</p>"
    if running:
        body += (
            "<p class='note'>План готується (1–3 хв), сторінка оновиться сама. "
            "Можна закрити її — результат збережеться.</p>"
        )
    if report is None:
        if not running:
            body += "<p class='note'>Плану на цей місяць ще немає.</p>"
        return _page("Контент-план M&D", body, refresh=running)
    d = report.data
    goals = "".join(f"<li>{escape(g)}</li>" for g in d.get("goals") or [])
    body += (
        f"<section><h2>{escape(d.get('theme', ''))}</h2>"
        + (f"<ul class='list'>{goals}</ul>" if goals else "")
        + f"<p class='muted'>Постів: {len(d.get('posts') or [])} · {escape(report.model)} · "
        f"${report.cost_usd:.2f} · {report.created_at.astimezone(UTC):%d.%m %H:%M} UTC</p>"
        "</section>"
    )
    cards = ""
    for i, p in enumerate(d.get("posts") or []):
        uid = f"p{report.id}_{i}"
        try:
            pd = date.fromisoformat(p.get("date", ""))
            when = f"{_day(pd)} {escape(p.get('time', ''))}"
        except ValueError:
            when = escape(p.get("date", ""))
        tags = " ".join("#" + t.lstrip("#") for t in p.get("hashtags") or [])
        caption = p.get("caption", "") + (f"\n\n{tags}" if tags else "")
        cards += (
            f"<div class='card'><div class='head'><b>{when}</b><span>"
            f"<span class='tag'>{escape(PLATFORMS.get(p.get('platform'), ''))}</span>"
            f"<span class='tag'>{escape(p.get('format', ''))}</span>"
            f"<span class='tag'>{escape(p.get('rubric', ''))}</span></span></div>"
            f"<h3>{escape(p.get('title', ''))}</h3>"
            + _copy_block(uid + "c", "Підпис і хештеги", caption)
            + f"<p class='muted'>Заклик: {escape(p.get('cta', ''))}</p>"
            + _copy_block(uid + "i", "Промпт для зображення", p.get("image_prompt", ""))
            + _copy_block(uid + "v", "Промпт для відео", p.get("video_prompt", ""))
            + "</div>"
        )
    body += f"<div class='cards'>{cards}</div>"
    return _page("Контент-план M&D", body, refresh=running)


@dataclass
class PanelDeps:
    """Що потрібно панелі крім дашборду (усе необовʼязкове — для тестів і без AI)."""

    get_day: Callable[[], Awaitable[DayStats]] | None = None
    hub: an.Hub | None = None
    get_engine: Callable[[], Any] | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)


def _recent_posts(engine: Any, now: datetime) -> list[PostStat]:
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        return list(
            s.scalars(
                select(PostStat)
                .where(PostStat.published_at >= now - timedelta(days=30))
                .order_by(PostStat.reach.desc())
                .limit(10)
            )
        )


def _parse_month(v: str | None, today: date) -> date:
    try:
        return datetime.strptime(v or "", "%Y-%m").date()
    except ValueError:
        return today.replace(day=1)


def build_router(
    get_settings: Callable[[], Settings],
    get_dashboard: Callable[[], Awaitable[Dashboard]],
    deps: PanelDeps | None = None,
) -> APIRouter:
    router = APIRouter()
    deps = deps or PanelDeps()

    def guard(request: Request) -> Response | None:
        settings = get_settings()
        if not settings.panel_password:
            return Response(status_code=404)
        if not _authed(request, settings):
            if request.method == "POST":
                return RedirectResponse("/panel", status_code=303)
            return HTMLResponse(login_page())
        return None

    def ai_on() -> bool:
        return deps.hub is not None and deps.hub.enabled

    @router.get("/panel", response_class=HTMLResponse)
    async def panel(request: Request) -> Response:
        if (r := guard(request)) is not None:
            return r
        x = Extras(ai_enabled=ai_on())
        if deps.get_day is not None:
            x.day = await deps.get_day()
        if deps.get_engine is not None:
            engine = deps.get_engine()
            x.report = an.latest(engine, "daily")
            x.posts = _recent_posts(engine, deps.clock())
        if deps.hub is not None:
            x.running = "daily" in deps.hub.running
            x.error = deps.hub.errors.get("daily", "")
        return HTMLResponse(render(await get_dashboard(), extras=x))

    @router.post("/panel/ai/daily")
    async def run_daily(request: Request) -> Response:
        if (r := guard(request)) is not None:
            return r
        if ai_on():
            deps.hub.start_daily()  # type: ignore[union-attr]
        return RedirectResponse("/panel#ai", status_code=303)

    @router.get("/panel/content", response_class=HTMLResponse)
    async def content(request: Request, m: str | None = None) -> Response:
        if (r := guard(request)) is not None:
            return r
        tz = get_settings().zone
        month = _parse_month(m, deps.clock().astimezone(tz).date())
        report = an.latest(deps.get_engine(), "content_plan", month) if deps.get_engine else None
        key = f"plan:{month:%Y-%m}"
        hub = deps.hub
        return HTMLResponse(
            render_content(
                month,
                report,
                ai_enabled=ai_on(),
                running=bool(hub and key in hub.running),
                error=hub.errors.get(key, "") if hub else "",
            )
        )

    @router.post("/panel/content/generate")
    async def generate(request: Request, month: str = Form("")) -> Response:
        if (r := guard(request)) is not None:
            return r
        tz = get_settings().zone
        m = _parse_month(month, deps.clock().astimezone(tz).date())
        if ai_on():
            deps.hub.start_plan(m)  # type: ignore[union-attr]
        return RedirectResponse(f"/panel/content?m={m:%Y-%m}", status_code=303)

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
