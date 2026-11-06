"""Контент-план: розклад, фото, ідеї, підтвердити / відхилити (3 відхилення → нова тема)."""

import io
import json
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import panel
from app.ai.gemini import ImageResult
from app.ai.jobs import Background
from app.config import Settings
from app.content import web
from app.content.schedule import month_slots
from app.content.storage import Media, PhotoError
from app.content.studio import MAX_REJECTIONS, Studio
from app.db.models import AiUsage, ContentItem, ContentPhoto
from app.notify import Notifier
from app.scheduler import Jobs
from tests.test_ai_analyst import FakeAnthropic, message

NOW = datetime(2026, 11, 25, 8, 0, tzinfo=UTC)
DEC = date(2026, 12, 1)


def jpeg(w=1200, h=900, color=(180, 140, 90), exif_gps=False) -> bytes:
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    if exif_gps:
        ex = Image.Exif()
        ex[0x0112] = 6  # повернути на 90°
        ex[0x8825] = {1: "N", 2: (50.0, 27.0, 0.0)}  # GPS
        img.save(buf, "JPEG", exif=ex)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


def settings(**kw):
    return Settings(_env_file=None, anthropic_api_key="k", gemini_api_key="g", **kw)


class FakeGemini:
    def __init__(self):
        self.calls = []

    async def image(self, model, prompt, *, aspect_ratio="4:5", source=None, **kw):
        self.calls.append(
            {"model": model, "prompt": prompt, "ratio": aspect_ratio, "source": source}
        )
        return ImageResult(jpeg(800, 1000, (90, 120, 100)), "image/jpeg", "")


def idea(slot=None, topic="Блонд без жовтизни", photo_id=0, **kw):
    d = {"topic": topic, "caption": "Текст поста", "hashtags": ["#блонд", "салон"],
         "cta": "Запис у Direct", "photo_id": photo_id, "photo_note": "Зніміть фарбування",
         "edit_prompt": "Crop tighter"}  # fmt: skip
    if slot is not None:
        d["slot"] = slot
    return {**d, **kw}


@pytest.fixture
def media(tmp_path):
    return Media(tmp_path / "media")


def make(engine, media, *steps, gemini=True, **kw):
    claude = FakeAnthropic(*steps)
    st = Studio(engine, settings(**kw), media, claude=claude,
                gemini=FakeGemini() if gemini else None, clock=lambda: NOW)  # fmt: skip
    return st, claude


# --- розклад ------------------------------------------------------------------


def test_plural():
    assert [web.plural(n, "пост", "пости", "постів") for n in (1, 4, 5, 11, 21, 22)] == [
        "1 пост", "4 пости", "5 постів", "11 постів", "21 пост", "22 пости"]  # fmt: skip


def test_slots_week_post_and_story_every_two_days():
    dec = month_slots(DEC, post_weekday=3, story_every=2)
    posts = [s.day.day for s in dec if s.kind == "post"]
    stories = [s.day.day for s in dec if s.kind == "story"]
    assert posts == [3, 10, 17, 24, 31]  # четверги грудня 2026
    assert stories == list(range(1, 32, 2)) and len(stories) == 16
    assert [s.kind for s in dec if s.day.day == 3] == ["post", "story"]
    nov = month_slots(date(2026, 11, 1), post_weekday=3, story_every=2)
    assert sum(s.kind == "post" for s in nov) == 4 and sum(s.kind == "story" for s in nov) == 15


# --- фото ---------------------------------------------------------------------


def test_upload_strips_exif_and_rotates(media):
    name, w, h = media.save_upload(jpeg(1200, 900, exif_gps=True))
    img = Image.open(media.path(name))
    assert (w, h) == (900, 1200) == img.size  # повернуто за EXIF
    assert not img.getexif()  # ні орієнтації, ні геолокації
    assert media.thumb_path(name).is_file()


def test_upload_rejects_garbage_and_paths(media):
    with pytest.raises(PhotoError, match="Це не фото"):
        media.save_upload(b"<script>")
    with pytest.raises(PhotoError, match="20 МБ"):
        media.save_upload(b"0" * (21 * 1024 * 1024))
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    with pytest.raises(PhotoError, match="GIF"):
        media.save_upload(gif.getvalue())
    for bad in ("../x.jpg", ".env", "a/b.jpg"):
        with pytest.raises(PhotoError):
            media.path(bad)


async def test_describe_photo_with_vision(engine, media):
    st, claude = make(engine, media, message({"description": "Фарбування блонд, денне світло",
                                              "category": "work", "quality": "poor"}))  # fmt: skip
    pid = st.add_photo(jpeg(), "IMG_1.jpg")
    await st.describe_photo(pid)
    (req,) = claude.requests
    assert req["model"] == "claude-haiku-5-5" and "fallbacks" not in req  # у Haiku fallback немає
    blocks = req["messages"][0]["content"]
    assert blocks[0]["type"] == "image" and blocks[0]["source"]["media_type"] == "image/jpeg"
    with Session(engine) as s:
        p = s.get(ContentPhoto, pid)
        assert p.category == "work" and "Якість слабка" in p.description
        assert s.scalar(select(AiUsage.kind)) == "vision"


# --- ідеї ---------------------------------------------------------------------


async def test_generate_month_fills_free_slots(engine, media):
    st, _ = make(engine, media)
    pid = st.add_photo(jpeg())
    n_slots = len(st.slots(DEC))
    items = [idea(i, topic=f"Тема {i}", photo_id=pid if i == 0 else 999) for i in range(n_slots)]
    st.claude.responses.append(message({"items": items}))
    assert await st.generate_month(date(2026, 12, 9)) == n_slots == 21
    prompt = st.claude.requests[0]["messages"][0]["content"]
    assert '"kind": "post"' in prompt and '"date": "2026-12-03"' in prompt
    assert '"photo_library"' in prompt and f'"id": {pid}' in prompt
    rows = st.items(DEC)
    story, post = rows[0], next(r for r in rows if r.kind == "post")  # 1.12 — вівторок, сторіс
    assert story.slot_date == DEC and story.photo_id == pid and story.photo_note == ""
    assert rows[1].photo_id is None and rows[1].photo_note  # неіснуюче фото → потрібне нове
    assert json.loads(post.hashtags) == ["блонд", "салон"] and json.loads(story.hashtags) == []
    assert all(r.status == "idea" for r in rows)
    assert await st.generate_month(DEC) == 0  # усі слоти зайняті — без виклику AI
    assert len(st.claude.requests) == 1


def add_item(engine, kind="post", photo_id=None, status="idea", day=3):
    with Session(engine) as s, s.begin():
        it = ContentItem(month=DEC, slot_date=date(2026, 12, day), kind=kind, status=status,
                         topic="Блонд", caption="Текст", hashtags='["блонд"]', cta="Direct",
                         photo_id=photo_id, edit_prompt="Crop tighter")  # fmt: skip
        s.add(it)
        s.flush()
        return it.id


async def test_reject_two_variants_then_new_topic(engine, media):
    st, claude = make(engine, media)
    iid = add_item(engine)
    modes = []
    for i in range(MAX_REJECTIONS):
        mode = st.reject(iid, f"Не те {i}")
        modes.append(mode)
        claude.responses.append(message(idea(topic=f"Варіант {i}")))
        await st.rework(iid, mode)
    assert modes == ["variant", "variant", "new_topic"]
    assert "залиш ту саму тему" in claude.requests[0]["messages"][0]["content"].lower()
    last = claude.requests[-1]["messages"][0]["content"]
    assert "ПОВНІСТЮ НОВУ" in last and "Не те 0" in last and "Не те 2" in last
    with Session(engine) as s:
        it = s.get(ContentItem, iid)
        assert (it.rejections, it.topics_tried, it.status) == (0, 2, "idea")
        assert it.topic == "Варіант 2" and len(json.loads(it.history)) == 3
    assert st.reject(iid) == "variant"  # нова тема — знову 3 спроби


async def test_reject_only_ideas(engine, media):
    st, _ = make(engine, media)
    iid = add_item(engine)
    st.approve(iid)
    with pytest.raises(ValueError, match="вже підтверджено"):
        st.approve(iid)
    with pytest.raises(ValueError, match="Відхилити можна лише ідею"):
        st.reject(iid)


# --- фото до пункту -----------------------------------------------------------


async def test_photo_edit_reject_twice_then_new_photo(engine, media):
    st, _ = make(engine, media)
    pid = st.add_photo(jpeg())
    iid = add_item(engine, kind="story", photo_id=pid, day=5)
    assert st.approve(iid) is True
    for i in range(MAX_REJECTIONS):
        await st.edit_image(iid)
        call = st.gemini.calls[-1]
        assert call["ratio"] == "9:16" and call["source"] == media.read(st.photos()[0].file)
        assert "Do not change the people, faces" in call["prompt"]
        assert "Crop tighter" in call["prompt"]
        if i:
            assert f"фон {i - 1}" in call["prompt"]  # зауваження власника передано
        res = st.reject_image(iid, f"фон {i}")
    assert res == "new_photo"
    with Session(engine) as s:
        it = s.get(ContentItem, iid)
        assert it.photo_id is None and it.image_file is None and "інше фото" in it.photo_note
        assert s.scalar(select(AiUsage.kind).where(AiUsage.kind == "image")) == "image"


async def test_photo_approve_ready_publish(engine, media):
    st, _ = make(engine, media)
    pid = st.add_photo(jpeg())
    iid = add_item(engine, photo_id=pid)
    st.approve(iid)
    await st.edit_image(iid)
    st.approve_image(iid)
    with pytest.raises(ValueError, match="Фото вже в готовому пості"):
        st.delete_photo(pid)
    st.mark_published(iid)
    with Session(engine) as s:
        assert s.get(ContentItem, iid).status == "published"


async def test_use_original_without_gemini(engine, media):
    st, _ = make(engine, media, gemini=False)
    assert not st.can_edit_photos
    pid = st.add_photo(jpeg())
    iid = add_item(engine)
    st.approve(iid)
    with pytest.raises(ValueError, match="оберіть фото"):
        st.use_original(iid)
    st.set_photo(iid, pid)
    st.use_original(iid)
    with Session(engine) as s:
        assert s.get(ContentItem, iid).status == "ready"


async def test_budget_blocks_image(engine, media):
    st, _ = make(engine, media, ai_monthly_budget_usd=1)
    with Session(engine) as s, s.begin():
        s.add(AiUsage(provider="anthropic", kind="chat", model="m", cost_usd=0.99, created_at=NOW))
    pid = st.add_photo(jpeg())
    iid = add_item(engine, photo_id=pid)
    from app.ai.budget import BudgetExceeded

    with pytest.raises(BudgetExceeded):
        await st.edit_image(iid)
    assert st.gemini.calls == []


# --- планувальник -------------------------------------------------------------


async def test_monthly_ideas_notify(engine, media):
    sent = []

    async def admin(text, keyboard=None):
        sent.append(text)

    st, _ = make(engine, media)
    st.claude.responses.append(message({"items": [idea(i) for i in range(21)]}))
    jobs = Jobs(engine, settings(public_url="https://bot.md.ua"), Notifier(admin_sender=admin),
                clock=lambda: NOW, studio=st)  # fmt: skip
    await jobs.monthly_plan()
    assert "Ідеї на 12.2026 готові: 21" in sent[0]
    assert "https://bot.md.ua/panel/content?m=2026-12" in sent[0]


# --- сторінка -----------------------------------------------------------------


def client(engine, st, jobs=None):
    s = settings(panel_password="pass-1234")
    st.settings = s
    app = FastAPI()
    app.include_router(panel.build_router(lambda: s, None))
    jobs = jobs or Background()
    app.include_router(web.build_router(lambda: s, lambda: st, jobs, lambda: NOW))
    c = TestClient(app, base_url="https://testserver")
    c.jobs = jobs
    return c


def login(c):
    c.post("/panel/login", data={"password": "pass-1234"}, follow_redirects=False)
    return c


async def test_page_requires_login(engine, media):
    st, _ = make(engine, media)
    pid = st.add_photo(jpeg())
    name = st.photos()[0].file
    c = client(engine, st)
    assert "Пароль" in c.get("/panel/content").text
    assert c.get(f"/panel/content/media/{name}").status_code == 200  # сторінка входу, не фото
    assert "image" not in c.get(f"/panel/content/media/{name}").headers["content-type"]
    r = c.post(f"/panel/content/photos/{pid}/delete", follow_redirects=False)
    assert r.headers["location"] == "/panel" and st.photos()


async def test_page_flow(engine, media):
    st, _ = make(engine, media)
    with client(engine, st) as c:
        login(c)
        html = c.get("/panel/content?m=2026-12").text
        assert "грудень 2026" in html and "5 постів (щочетверга) і 16 сторіс (раз на 2 дні)" in html
        assert "Згенерувати ідеї · 21" in html and "Як це працює" in html

        r = c.post("/panel/content/photos", data={"month": "2026-12"},
                   files=[("files", ("a.jpg", jpeg(), "image/jpeg")),
                          ("files", ("b.txt", b"hello", "text/plain"))],
                   follow_redirects=False)  # fmt: skip
        assert r.status_code == 303 and "msg=" in r.headers["location"]  # b.txt відхилено
        assert len(st.photos()) == 1
        pid = st.photos()[0].id

        iid = add_item(engine, photo_id=None)
        with Session(engine) as s, s.begin():
            s.get(ContentItem, iid).caption = "Текст <b>жирно</b>"
        html = c.get("/panel/content?m=2026-12").text
        assert "Текст &lt;b&gt;жирно&lt;/b&gt;" in html and "<b>жирно" not in html
        assert "Підтвердити" in html and "Відхилити" in html and "Потрібне фото" in html

        r = c.post(f"/panel/content/items/{iid}/approve", follow_redirects=False)
        assert r.headers["location"] == f"/panel/content?m=2026-12#item-{iid}"
        html = c.get("/panel/content?m=2026-12&f=approved").text
        assert "Взяти це фото" in html and "Відхилити" not in html

        c.post(f"/panel/content/items/{iid}/photo", data={"photo_id": pid})
        await_jobs(c)
        html = c.get("/panel/content?m=2026-12").text
        assert "Після обробки AI" in html and "Фото підходить" in html

        c.post(f"/panel/content/items/{iid}/image/approve")
        html = c.get("/panel/content?m=2026-12").text
        assert "Завантажити фото" in html and "Опубліковано ✓" in html
        with Session(engine) as s:
            img = s.get(ContentItem, iid).image_file
        r = c.get(f"/panel/content/media/{img}?download=1")
        assert r.headers["content-type"] == "image/jpeg"
        assert "attachment" in r.headers["content-disposition"]
        assert c.get("/panel/content/media/..%2F..%2Fsecret").status_code == 404


async def test_page_reject_runs_rework(engine, media):
    st, claude = make(engine, media, message(idea(topic="Новий кут")))
    iid = add_item(engine)
    with client(engine, st) as c:
        login(c)
        c.post(f"/panel/content/items/{iid}/reject", data={"reason": "Задовгий текст"})
        await_jobs(c)
        html = c.get("/panel/content?m=2026-12").text
    assert "Новий кут" in html and "Відхилень цієї теми: 1 з 3" in html
    assert "Задовгий текст" in claude.requests[0]["messages"][0]["content"]


def await_jobs(c):
    """Фонові задачі живуть у циклі подій TestClient — чекаємо, поки вони завершаться."""
    import time

    for _ in range(300):
        if not c.jobs.running:
            return
        time.sleep(0.01)
    raise AssertionError(f"задачі не завершились: {c.jobs.running}")
