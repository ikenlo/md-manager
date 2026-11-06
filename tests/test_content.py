"""Контент-план: розклад, фото, ідеї, підтвердити / відхилити (3 відхилення → нова тема)."""

import io
import json
from datetime import UTC, date, datetime

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gemini import ImageResult
from app.config import Settings
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
    assert "https://bot.md.ua/#/content" in sent[0]


def test_before_after_compose_and_labels():
    from app.content.beforeafter import SIZE, compose

    out = Image.open(
        io.BytesIO(compose(jpeg(1200, 900, (200, 150, 100)), jpeg(800, 1200, (90, 60, 40))))
    )
    assert out.size == SIZE
    w, h = SIZE
    left, right = out.getpixel((w // 4, h // 2)), out.getpixel((3 * w // 4, h // 2))
    assert left[0] > 150 and right[0] < 120  # «до» ліворуч, «після» праворуч, кольори не змінено
    assert abs(left[0] - 200) < 12 and abs(right[0] - 90) < 12
    tag = out.getpixel((40, 40))
    assert tag[1] > tag[0] and tag[1] < 120  # темно-зелена плашка підпису «ДО»


def test_story_card_renders_text_in_both_scripts():
    from app.content.story_card import SIZE, Font, Story, render

    data = render(Story("цього тижня", "Є вільні віконця", ["Запис —"], [("Telegram-бот", "M&D")]))
    img = Image.open(io.BytesIO(data))
    assert img.size == SIZE
    f = Font("manrope", 40, 500)
    assert [t for t, _ in f.runs("Telegram-бот")] == ["Telegram-", "бот"]
    assert f.runs("бот")[0][1] is f.cyr and f.runs("M&D")[0][1] is f.lat
