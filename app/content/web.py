# ruff: noqa: E501 — HTML-шаблон, довгі рядки розмітки читаються краще цілими
"""Сторінка /panel/content: фото салону, ідеї постів і сторіс, підтвердити / відхилити, готові пости.

Вхід — той самий, що в панелі (cookie). Усі дії — звичайні форми з POST і поверненням на сторінку,
довгі дії AI йдуть у фоні (Background), сторінка сама оновлюється, поки вони тривають.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from html import escape
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from app import panel
from app.ai.analyst import next_month
from app.ai.jobs import Background
from app.config import Settings
from app.content.storage import PhotoError
from app.content.studio import CATEGORY_NAMES, MAX_REJECTIONS, Studio
from app.db.models import ContentItem, ContentPhoto
from app.web_style import page

WD = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]
WD_FULL = ["понеділка", "вівторка", "середи", "четверга", "пʼятниці", "суботи", "неділі"]
MONTHS = ["січень", "лютий", "березень", "квітень", "травень", "червень", "липень", "серпень",
          "вересень", "жовтень", "листопад", "грудень"]  # fmt: skip
MAX_FILES = 30

FILTERS = {
    "all": ("Усі", None),
    "idea": ("На розгляді", {"idea"}),
    "approved": ("Чекають фото", {"approved"}),
    "ready": ("Готові", {"ready"}),
    "published": ("Опубліковані", {"published"}),
}
STATUS = {
    "idea": ("warn", "На розгляді"),
    "approved": ("info", "Підтверджено · фото"),
    "ready": ("ok", "Готово до публікації"),
    "published": ("", "Опубліковано"),
}

COPY_JS = (
    "document.addEventListener('click',e=>{const b=e.target.closest('[data-copy]');if(!b)return;"
    "const t=document.getElementById(b.dataset.copy);if(!t)return;const done=()=>{const o=b.textContent;"
    "b.textContent='Скопійовано';setTimeout(()=>b.textContent=o,1500)};"
    "const sel=()=>{const r=document.createRange();r.selectNodeContents(t);"
    "const s=getSelection();s.removeAllRanges();s.addRange(r)};"
    "try{navigator.clipboard.writeText(t.textContent).then(done,sel)}catch(_){sel()}});"
    "document.querySelectorAll('input[type=file][data-auto]').forEach(i=>i.addEventListener('change',"
    "()=>{if(i.files.length)i.form.submit()}));"
)


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


def month_name(m: date) -> str:
    return f"{MONTHS[m.month - 1]} {m.year}"


def _parse_month(v: str | None, today: date) -> date:
    try:
        return datetime.strptime(v or "", "%Y-%m").date()
    except ValueError:
        return today.replace(day=1)


@dataclass
class View:
    month: date
    items: list[ContentItem]
    photos: list[ContentPhoto]
    jobs: Background
    studio: Studio
    flt: str = "all"
    msg: str = ""


def _img(name: str, alt: str, label: str) -> str:
    n = quote(name)
    return (
        f"<figure style='margin:0;min-width:0'><a href='/panel/content/media/{n}' target='_blank' "
        f"rel='noopener'><img src='/panel/content/thumb/{n}' alt='{escape(alt)}' loading='lazy' "
        "style='width:100%;aspect-ratio:4/5;object-fit:cover;border-radius:10px;display:block;"
        "background:var(--surface-3)'></a>"
        f"<figcaption class='small muted' style='margin-top:4px'>{escape(label)}</figcaption></figure>"
    )


def _form(action: str, inner: str, *, multipart: bool = False, style: str = "") -> str:
    enc = " enctype='multipart/form-data'" if multipart else ""
    return f"<form method='post' action='{action}'{enc} class='row' style='{style}'>{inner}</form>"


def _upload_form(month: date, item_id: int | None = None, label: str = "Завантажити фото") -> str:
    uid = f"up{item_id or 0}"
    hidden = f"<input type='hidden' name='item_id' value='{item_id}'>" if item_id else ""
    return _form(
        "/panel/content/photos",
        f"<input type='hidden' name='month' value='{month:%Y-%m}'>{hidden}"
        f"<label class='btn sm' for='{uid}' style='cursor:pointer'>{label}</label>"
        f"<input id='{uid}' type='file' name='files' accept='image/jpeg,image/png,image/webp' "
        f"{'' if item_id else 'multiple '}data-auto required style='position:absolute;width:1px;"
        "height:1px;opacity:0;min-height:0;padding:0;border:0'>"
        "<noscript><button class='btn sm' type='submit'>Надіслати</button></noscript>",
        multipart=True,
    )


def _photo_picker(v: View, it: ContentItem) -> str:
    opts = "".join(
        f"<option value='{p.id}'>#{p.id} · {escape(CATEGORY_NAMES.get(p.category, 'Фото'))}"
        f"{' — ' + escape(p.description[:60]) if p.description else ''}</option>"
        for p in v.photos
    )
    if not opts:
        return ""
    return _form(
        f"/panel/content/items/{it.id}/photo",
        f"<select name='photo_id' aria-label='Фото з бібліотеки' style='flex:1;min-width:0'>{opts}</select>"
        "<button class='btn sm' type='submit'>Взяти це фото</button>",
        style="flex-wrap:nowrap",
    )


def _counter(n: int, what: str, then: str) -> str:
    if not n:
        return ""
    return (
        f"<p class='small muted' style='margin:6px 0 0'>Відхилень {what}: {n} з {MAX_REJECTIONS}. "
        f"Після {MAX_REJECTIONS}-го {then}.</p>"
    )


def _item(v: View, it: ContentItem, photos: dict[int, ContentPhoto]) -> str:
    s = v.studio.settings
    busy_text = f"item:{it.id}" in v.jobs.running
    busy_img = f"image:{it.id}" in v.jobs.running
    err = v.jobs.errors.get(f"item:{it.id}") or v.jobs.errors.get(f"image:{it.id}")
    is_post = it.kind == "post"
    when = f"{WD[it.slot_date.weekday()]} {it.slot_date:%d.%m} · " + (
        s.content_post_time if is_post else s.content_story_time
    )
    cls, label = STATUS.get(it.status, ("", it.status))
    head = (
        f"<div class='row' style='justify-content:space-between'><b>{when}</b><span class='row'>"
        f"<span class='chip {'prog' if is_post else 'gold'}'>{'Пост' if is_post else 'Сторіс'}</span>"
        f"<span class='chip {cls}'>{label}</span></span></div>"
    )
    if busy_text:
        return (
            f"<div class='card' id='item-{it.id}'>{head}<p class='callout' style='margin-top:12px'>"
            "AI готує новий варіант — сторінка оновиться сама.</p></div>"
        )
    tags = json.loads(it.hashtags or "[]")
    text = it.caption + ("\n\n" + " ".join("#" + t for t in tags) if tags else "")
    body = (
        f"<h3 class='serif' style='font-size:22px;margin:10px 0 2px'>{escape(it.topic)}</h3>"
        + (f"<p class='small muted' style='margin:0 0 8px'>Тема №{it.topics_tried}</p>"
           if it.topics_tried > 1 else "<div style='height:8px'></div>")
        + f"<div class='row' style='justify-content:space-between;margin-bottom:6px'>"
        f"<span class='small muted'>{'Підпис і хештеги' if is_post else 'Текст на сторіс'}</span>"
        f"<button type='button' class='btn sm ghost' data-copy='t{it.id}'>Копіювати</button></div>"
        f"<pre class='p' id='t{it.id}'>{escape(text)}</pre>"
        f"<p class='small' style='margin:8px 0 0'><span class='muted'>"
        f"{'Заклик' if is_post else 'Наліпка'}:</span> {escape(it.cta)}</p>"
    )  # fmt: skip

    # фото
    src = photos.get(it.photo_id or 0)
    pics = ""
    if src is not None:
        pics = _img(src.file, "Фото салону", "Ваше фото")
        if it.image_file:
            pics += _img(it.image_file, "Оброблене фото", "Після обробки AI")
        elif busy_img:
            pics += ("<div class='callout' style='display:grid;place-items:center;text-align:center'>"
                     "AI підправляє фото…</div>")  # fmt: skip
        pics = (
            f"<div class='grid' style='grid-template-columns:1fr 1fr;margin-top:12px'>{pics}</div>"
        )
    else:
        note = it.photo_note or "Потрібне фото до цього пункту."
        pics = (
            f"<div class='callout' style='margin-top:12px'><b>Потрібне фото.</b> {escape(note)}</div>"
            f"<div class='row' style='margin-top:8px'>{_upload_form(v.month, it.id, 'Завантажити своє')}"
            f"</div>{_photo_picker(v, it)}"
        )

    # дії
    acts = ""
    if err:
        acts += f"<p class='callout danger' style='margin-top:12px'>{escape(err)}</p>"
    base = f"/panel/content/items/{it.id}"
    if it.status == "idea":
        acts += (
            "<div class='row' style='margin-top:14px'>"
            + _form(f"{base}/approve", "<button class='btn ok' type='submit'>Підтвердити</button>")
            + "</div>"
            + _form(
                f"{base}/reject",
                "<input name='reason' maxlength='500' placeholder='Що не так? (необовʼязково)' "
                "aria-label='Причина відхилення' style='flex:1;min-width:0'>"
                "<button class='btn danger' type='submit'>Відхилити</button>",
                style="margin-top:8px;flex-wrap:nowrap",
            )
            + _counter(it.rejections, "цієї теми", "AI придумає нову тему з нуля")
        )
    elif it.status == "approved" and src is not None and not busy_img:
        if it.image_status == "ready":
            acts += (
                "<div class='row' style='margin-top:14px'>"
                + _form(f"{base}/image/approve",
                        "<button class='btn ok' type='submit'>Фото підходить</button>")
                + "</div>"
                + _form(
                    f"{base}/image/reject",
                    "<input name='reason' maxlength='500' placeholder='Що змінити на фото?' "
                    "aria-label='Що змінити на фото' style='flex:1;min-width:0'>"
                    "<button class='btn danger' type='submit'>Переробити</button>",
                    style="margin-top:8px;flex-wrap:nowrap",
                )
                + _counter(it.image_rejections, "фото", "треба буде обрати інше фото")
            )  # fmt: skip
        else:
            btn = (
                "<button class='btn primary' type='submit'>Обробити фото</button>"
                if v.studio.can_edit_photos
                else ""
            )
            acts += (
                "<div class='row' style='margin-top:14px'>"
                + (_form(f"{base}/image/retry", btn) if btn else "")
                + _form(f"{base}/image/original",
                        "<button class='btn' type='submit'>Взяти без обробки</button>")
                + "</div>"
            )  # fmt: skip
    elif it.status == "ready":
        img = it.image_file or (src.file if src else "")
        dl = (
            f"<a class='btn primary' href='/panel/content/media/{quote(img)}?download=1'>"
            "Завантажити фото</a>"
            if img
            else ""
        )
        acts += (
            f"<div class='row' style='margin-top:14px'>{dl}"
            f"<button type='button' class='btn' data-copy='t{it.id}'>Копіювати текст</button>"
            + _form(
                f"{base}/published",
                "<button class='btn ghost' type='submit'>Опубліковано ✓</button>",
            )
            + "</div>"
        )
    return f"<div class='card' id='item-{it.id}'>{head}{body}{pics}{acts}</div>"


def _photos_card(v: View) -> str:
    busy = {int(k.split(":")[1]) for k in v.jobs.running if k.startswith("photo:")}
    tiles = ""
    for p in v.photos:
        desc = "AI описує фото…" if p.id in busy else (p.description or "Без опису")
        tiles += (
            "<div style='min-width:0'>"
            + _img(p.file, p.description or "Фото салону", f"#{p.id} · {CATEGORY_NAMES.get(p.category, 'Фото')}")
            + f"<p class='small muted' style='margin:2px 0 4px'>{escape(desc[:140])}</p>"
            + _form(f"/panel/content/photos/{p.id}/delete",
                    f"<input type='hidden' name='month' value='{v.month:%Y-%m}'>"
                    "<button class='btn sm ghost' type='submit' style='color:var(--danger);padding:0'>"
                    "Видалити</button>")
            + "</div>"
        )  # fmt: skip
    grid = (
        f"<div class='grid' style='grid-template-columns:repeat(auto-fill,minmax(140px,1fr));"
        f"margin-top:12px'>{tiles}</div>"
        if tiles
        else "<p class='callout' style='margin-top:12px'>Фото ще немає. Завантажте 10–20 фото: "
        "роботи майстрів, інтерʼєр, процес — AI підбере їх до постів.</p>"
    )
    return (
        "<details class='card' open><summary class='card-head' style='cursor:pointer;margin:0'>"
        f"<h3>Фото салону · {len(v.photos)}</h3>"
        f"<span class='row'>{_upload_form(v.month)}</span></summary>"
        "<p class='small muted' style='margin:8px 0 0'>Лише фото, на публікацію яких клієнтка "
        "погодилась. Геолокація й дані камери з фото видаляються автоматично.</p>"
        f"{grid}</details>"
    )


def render(v: View) -> str:
    s = v.studio.settings
    slots = v.studio.slots(v.month)
    n_posts = sum(1 for x in slots if x.kind == "post")
    n_story = len(slots) - n_posts
    by = {k: sum(1 for it in v.items if it.status == k) for k in STATUS}
    missing = len(slots) - len({(it.slot_date, it.kind) for it in v.items})
    gen_key = f"month:{v.month:%Y-%m}"
    gen_busy = gen_key in v.jobs.running
    busy = bool(v.jobs.running)

    prev_m = (v.month - timedelta(days=1)).replace(day=1)
    next_m = next_month(v.month)
    actions = (
        f"<a class='btn ghost' href='/panel/content?m={prev_m:%Y-%m}'>← {MONTHS[prev_m.month - 1]}</a>"
        f"<a class='btn ghost' href='/panel/content?m={next_m:%Y-%m}'>{MONTHS[next_m.month - 1]} →</a>"
    )
    if v.studio.can_write and missing and not gen_busy:
        actions += _form(
            "/panel/content/generate",
            f"<input type='hidden' name='month' value='{v.month:%Y-%m}'>"
            f"<button class='btn primary' type='submit'>Згенерувати ідеї · {missing}</button>",
        )
    body = (
        "<div class='topbar'><div><h1>Контент-план</h1><div class='sub'>Instagram і Facebook · "
        f"{month_name(v.month)} · {plural(n_posts, 'пост', 'пости', 'постів')} "
        f"(що{WD_FULL[s.content_post_weekday]}) і {n_story} сторіс "
        f"(раз на {plural(s.content_story_every_days, 'день', 'дні', 'днів')})</div></div>"
        f"<div class='row'>{actions}</div></div>"
    )
    if v.msg:
        body += f"<p class='callout danger' style='margin-bottom:12px'>{escape(v.msg)}</p>"
    if not v.studio.can_write:
        body += ("<p class='callout' style='margin-bottom:12px'>Щоб AI пропонував ідеї, потрібен "
                 "ANTHROPIC_API_KEY.</p>")  # fmt: skip
    if not v.studio.can_edit_photos:
        body += ("<p class='callout' style='margin-bottom:12px'>Обробка фото вимкнена (немає "
                 "GEMINI_API_KEY) — фото можна брати без обробки.</p>")  # fmt: skip
    if gen_busy:
        body += ("<p class='callout' style='margin-bottom:12px'>AI придумує ідеї на місяць "
                 "(1–2 хв). Сторінка оновиться сама — можна закрити її.</p>")  # fmt: skip
    if err := v.jobs.errors.get(gen_key):
        body += f"<p class='callout danger' style='margin-bottom:12px'>{escape(err)}</p>"
    body += (
        "<div class='grid kpi'>"
        f"<div class='card kpi-tile dark'><span class='kpi-label'>Чекають вашого рішення</span>"
        f"<span class='kpi-value'>{by['idea']}</span></div>"
        f"<div class='card kpi-tile'><span class='kpi-label'>Підтверджено, готуємо фото</span>"
        f"<span class='kpi-value'>{by['approved']}</span></div>"
        f"<div class='card kpi-tile accent'><span class='kpi-label'>Готово до публікації</span>"
        f"<span class='kpi-value'>{by['ready']}</span></div>"
        f"<div class='card kpi-tile'><span class='kpi-label'>Опубліковано</span>"
        f"<span class='kpi-value'>{by['published']}</span></div></div>"
        f"<div class='section'>{_photos_card(v)}</div>"
    )
    seg = "".join(
        f"<a class='{'on' if k == v.flt else ''}' href='/panel/content?m={v.month:%Y-%m}&f={k}'>"
        f"{lbl}{f' · {by[k]}' if k in by and by[k] else ''}</a>"
        for k, (lbl, _) in FILTERS.items()
    )
    allowed = FILTERS.get(v.flt, FILTERS["all"])[1]
    shown = [it for it in v.items if allowed is None or it.status in allowed]
    photos = {p.id: p for p in v.photos}
    cards = "".join(_item(v, it, photos) for it in shown)
    if not v.items:
        cards = (
            "<div class='card'><h3>Як це працює</h3><ol style='margin:10px 0 0;padding-left:20px;"
            "display:grid;gap:6px'><li>Завантажте фото салону — AI сам опише, що на них.</li>"
            "<li>Натисніть «Згенерувати ідеї»: AI розпише пости й сторіс на місяць.</li>"
            "<li>Кожну ідею підтвердіть або відхиліть з коротким поясненням. Після двох відхилень "
            "AI змінює подачу, після третього — придумує іншу тему.</li>"
            "<li>AI трохи підправляє ваше фото під стиль стрічки, не змінюючи результат роботи.</li>"
            "<li>Завантажте готове фото, скопіюйте текст — і публікуйте.</li></ol></div>"
        )
    elif not shown:
        cards = "<p class='callout'>У цьому фільтрі порожньо.</p>"
    body += (
        f"<div class='section row' style='justify-content:space-between'><div class='seg'>{seg}</div>"
        "</div>"
        f"<div class='section grid two'>{cards}</div>"
    )
    if by["idea"] and not busy:
        body += (
            "<details class='section'><summary class='small muted' style='cursor:pointer'>"
            "Почати ідеї місяця заново</summary><div class='card' style='margin-top:8px'>"
            "<p class='small' style='margin:0 0 10px'>Усі непідтверджені ідеї буде видалено, "
            "підтверджені й готові лишаться. Потім натисніть «Згенерувати ідеї».</p>"
            + _form("/panel/content/reset",
                    f"<input type='hidden' name='month' value='{v.month:%Y-%m}'>"
                    f"<button class='btn danger' type='submit'>Видалити {by['idea']} ідей</button>")
            + "</div></details>"
        )  # fmt: skip
    return page("Контент-план M&D", body, active="content", refresh=busy, script=COPY_JS)


def build_router(
    get_settings: Callable[[], Settings],
    get_studio: Callable[[], Studio | None],
    jobs: Background,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> APIRouter:
    router = APIRouter()

    def guard(request: Request) -> Response | None:
        settings = get_settings()
        if not settings.panel_password or get_studio() is None:
            return Response(status_code=404)
        if not panel._authed(request, settings):
            if request.method == "POST":
                return RedirectResponse("/panel", status_code=303)
            return HTMLResponse(panel.login_page())
        return None

    def back(month: date | None, item_id: int | None = None, msg: str = "") -> Response:
        url = f"/panel/content?m={month:%Y-%m}" if month else "/panel/content"
        if msg:
            url += ("&" if month else "?") + "msg=" + quote(msg)
        if item_id:
            url += f"#item-{item_id}"
        return RedirectResponse(url, status_code=303)

    def today() -> date:
        return clock().astimezone(get_settings().zone).date()

    def item_month(st: Studio, item_id: int) -> date | None:
        from sqlalchemy.orm import Session

        with Session(st.engine) as s:
            it = s.get(ContentItem, item_id)
            return it.month if it else None

    @router.get("/panel/content", response_class=HTMLResponse)
    async def view(
        request: Request, m: str | None = None, f: str = "all", msg: str = ""
    ) -> Response:
        if (r := guard(request)) is not None:
            return r
        st = get_studio()
        assert st is not None
        month = _parse_month(m, today())
        v = View(month, st.items(month), st.photos(), jobs, st, f if f in FILTERS else "all", msg)
        return HTMLResponse(render(v))

    @router.post("/panel/content/generate")
    async def generate(request: Request, month: str = Form("")) -> Response:
        if (r := guard(request)) is not None:
            return r
        st = get_studio()
        m = _parse_month(month, today())
        if st and st.can_write:
            jobs.start(f"month:{m:%Y-%m}", lambda: st.generate_month(m))
        return back(m)

    @router.post("/panel/content/reset")
    async def reset(request: Request, month: str = Form("")) -> Response:
        if (r := guard(request)) is not None:
            return r
        m = _parse_month(month, today())
        get_studio().reset_month(m)  # type: ignore[union-attr]
        return back(m)

    @router.post("/panel/content/photos")
    async def upload(
        request: Request,
        files: list[UploadFile] = File(...),  # noqa: B008
        month: str = Form(""),
        item_id: int | None = Form(None),
    ) -> Response:
        if (r := guard(request)) is not None:
            return r
        st = get_studio()
        assert st is not None
        m = _parse_month(month, today())
        errors: list[str] = []
        added: list[int] = []
        for up in files[:MAX_FILES]:
            try:
                added.append(st.add_photo(await up.read(), up.filename or ""))
            except PhotoError as e:
                errors.append(f"{up.filename}: {e}")
        if len(files) > MAX_FILES:
            errors.append(f"За раз — до {MAX_FILES} фото, решту надішліть ще раз.")
        if st.can_write:
            for pid in added:
                jobs.start(f"photo:{pid}", lambda pid=pid: st.describe_photo(pid))
        if item_id and added:
            try:
                st.set_photo(item_id, added[0])
                if st.can_edit_photos and _status(st, item_id) == "approved":
                    jobs.start(f"image:{item_id}", lambda: st.edit_image(item_id))
            except ValueError as e:
                errors.append(str(e))
        return back(m, item_id, "; ".join(errors))

    @router.post("/panel/content/photos/{photo_id}/delete")
    async def delete_photo(request: Request, photo_id: int, month: str = Form("")) -> Response:
        if (r := guard(request)) is not None:
            return r
        m = _parse_month(month, today())
        try:
            get_studio().delete_photo(photo_id)  # type: ignore[union-attr]
        except ValueError as e:
            return back(m, msg=str(e))
        return back(m)

    @router.get("/panel/content/media/{name}")
    async def media(request: Request, name: str, download: int = 0) -> Response:
        return _file(request, name, download, thumb=False)

    @router.get("/panel/content/thumb/{name}")
    async def thumb(request: Request, name: str) -> Response:
        return _file(request, name, 0, thumb=True)

    def _file(request: Request, name: str, download: int, *, thumb: bool) -> Response:
        if (r := guard(request)) is not None:
            return r
        st = get_studio()
        assert st is not None
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
        from sqlalchemy.orm import Session

        with Session(st.engine) as s:
            it = s.get(ContentItem, item_id)
            return it.status if it else ""

    async def _act(request: Request, item_id: int, fn: Callable[[Studio], None]) -> Response:
        if (r := guard(request)) is not None:
            return r
        st = get_studio()
        assert st is not None
        m = item_month(st, item_id)
        if f"item:{item_id}" in jobs.running or f"image:{item_id}" in jobs.running:
            return back(m, item_id, "AI ще працює над цим пунктом — зачекайте хвилину.")
        try:
            fn(st)
        except ValueError as e:
            return back(m, item_id, str(e))
        return back(m, item_id)

    @router.post("/panel/content/items/{item_id}/approve")
    async def approve(request: Request, item_id: int) -> Response:
        def do(st: Studio) -> None:
            if st.approve(item_id) and st.can_edit_photos:
                jobs.start(f"image:{item_id}", lambda: st.edit_image(item_id))

        return await _act(request, item_id, do)

    @router.post("/panel/content/items/{item_id}/reject")
    async def reject(request: Request, item_id: int, reason: str = Form("")) -> Response:
        def do(st: Studio) -> None:
            if not st.can_write:
                raise ValueError("Щоб AI переробив ідею, потрібен ANTHROPIC_API_KEY")
            mode = st.reject(item_id, reason)
            jobs.start(f"item:{item_id}", lambda: st.rework(item_id, mode))

        return await _act(request, item_id, do)

    @router.post("/panel/content/items/{item_id}/photo")
    async def choose_photo(request: Request, item_id: int, photo_id: int = Form(...)) -> Response:
        def do(st: Studio) -> None:
            st.set_photo(item_id, photo_id)
            if st.can_edit_photos and _status(st, item_id) == "approved":
                jobs.start(f"image:{item_id}", lambda: st.edit_image(item_id))

        return await _act(request, item_id, do)

    @router.post("/panel/content/items/{item_id}/image/retry")
    async def image_retry(request: Request, item_id: int) -> Response:
        def do(st: Studio) -> None:
            jobs.start(f"image:{item_id}", lambda: st.edit_image(item_id))

        return await _act(request, item_id, do)

    @router.post("/panel/content/items/{item_id}/image/original")
    async def image_original(request: Request, item_id: int) -> Response:
        return await _act(request, item_id, lambda st: st.use_original(item_id))

    @router.post("/panel/content/items/{item_id}/image/approve")
    async def image_approve(request: Request, item_id: int) -> Response:
        return await _act(request, item_id, lambda st: st.approve_image(item_id))

    @router.post("/panel/content/items/{item_id}/image/reject")
    async def image_reject(request: Request, item_id: int, reason: str = Form("")) -> Response:
        def do(st: Studio) -> None:
            if st.reject_image(item_id, reason) == "retry" and st.can_edit_photos:
                jobs.start(f"image:{item_id}", lambda: st.edit_image(item_id))

        return await _act(request, item_id, do)

    @router.post("/panel/content/items/{item_id}/published")
    async def published(request: Request, item_id: int) -> Response:
        return await _act(request, item_id, lambda st: st.mark_published(item_id))

    return router
