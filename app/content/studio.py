"""Контент-план без маркетолога: AI пропонує ідеї, власник підтверджує або відхиляє,
фото дає салон — AI лише трохи підправляє їх для цілісної стрічки.

Життя одного пункту плану (ContentItem):
  idea ──підтвердити──▶ approved ──фото оброблено й підтверджено──▶ ready ──▶ published
   ▲  └─відхилити: 1-ше і 2-ге відхилення → видозмінений варіант тієї ж теми,
   │               3-тє → нова тема з нуля (лічильник обнуляється)
Фото: 1-ше і 2-ге відхилення → переробити з урахуванням зауваження,
      3-тє → відʼєднати фото, щоб обрати або завантажити інше.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.agent import usage
from app.ai import budget, prices
from app.ai.analyst import WD, _services_from_catalog, _services_local
from app.ai.claude_json import AiUnavailable, ask_json, obj
from app.config import Settings
from app.content.schedule import Slot, month_slots
from app.content.storage import Media
from app.db.models import ContentItem, ContentPhoto, PostStat

MAX_REJECTIONS = 3  # третє відхилення теми → нова тема; третє відхилення фото → інше фото

S = {"type": "string"}
CATEGORIES = ["work", "before_after", "interior", "master", "product", "other"]
CATEGORY_NAMES = {
    "work": "Робота", "before_after": "До/після", "interior": "Інтерʼєр",
    "master": "Майстер", "product": "Косметика", "other": "Інше",
}  # fmt: skip

IDEA_FIELDS = {
    "topic": S,
    "caption": S,
    "hashtags": {"type": "array", "items": S},
    "cta": S,
    "photo_id": {"type": "integer", "description": "id фото з бібліотеки або 0"},
    "photo_note": S,
    "edit_prompt": S,
}
IDEA_SCHEMA = obj(IDEA_FIELDS)
MONTH_SCHEMA = obj(
    {"items": {"type": "array", "items": obj({"slot": {"type": "integer"}, **IDEA_FIELDS})}}
)
PHOTO_SCHEMA = obj(
    {
        "description": S,
        "category": {"type": "string", "enum": CATEGORIES},
        "quality": {"type": "string", "enum": ["good", "ok", "poor"]},
    }
)

SYSTEM = (
    "Ти — SMM салону краси M&D (Київська область). Маркетолога в салоні немає: власник лише "
    "підтверджує або відхиляє твої ідеї і дає реальні фото салону. Тому кожна ідея має бути "
    "готовою до публікації без доопрацювання.\n"
    "Формати:\n"
    "- Пост (стрічка Instagram і Facebook): caption 400–900 символів — живий, теплий, на «ви», "
    "з користю для клієнтки; 5–10 хештегів без «#»; cta — один заклик (запис у Direct або "
    "через Telegram-бота).\n"
    "- Сторіс: caption — текст на сторіс, до 90 символів, 1–2 рядки; hashtags — порожній "
    "список; cta — наліпка: опитування з варіантами, питання або посилання на запис.\n"
    "Фото: обери з бібліотеки (photo_id) те, що пасує до теми, за описом. Одне фото — не "
    "частіше ніж раз на 2 тижні в межах місяця. Якщо доречного немає — photo_id = 0, а в "
    "photo_note просто опиши, що сфотографувати на телефон (кадр, світло, ракурс). Якщо фото "
    "є — photo_note порожній.\n"
    "edit_prompt — англійською, 1–2 речення: що трохи підправити на фото (кадрування, "
    "прибрати зайве з фону, вирівняти світло). Ніколи не змінюй результат послуги: зачіску, "
    "колір волосся, нігті, шкіру, обличчя.\n"
    "Не вигадуй цін, знижок, акцій чи імен — ціни лише з каталогу послуг. Чергуй теми: "
    "результати робіт, догляд і поради, майстри й атмосфера, послуги й сезон, відгуки. "
    "Ураховуй свята й сезон в Україні цього місяця."
)

STYLE = (
    "Lightly retouch this real photo from beauty salon M&D for a cohesive Instagram feed. "
    "Keep it natural and believable: warm soft daylight, gentle contrast, slightly muted "
    "deep-green and warm-gold tones, tidy background (remove small clutter such as cables, "
    "bottles or towels if distracting), straighten the horizon, crop to {ratio} with the "
    "subject well framed. Do not change the people, faces, hair colour, haircut, nails or "
    "skin — the result of the service must stay exactly as photographed. No text, no logos, "
    "no frames. "
)


def _ratio(kind: str) -> str:
    return "9:16" if kind == "story" else "4:5"


def _idea_dict(it: ContentItem) -> dict[str, Any]:
    return {
        "topic": it.topic,
        "caption": it.caption,
        "hashtags": json.loads(it.hashtags or "[]"),
        "cta": it.cta,
        "photo_id": it.photo_id or 0,
    }


class Studio:
    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        media: Media,
        *,
        claude: Any = None,
        gemini: Any = None,
        mds: Any = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.media = media
        self.claude = claude
        self.gemini = gemini
        self.mds = mds
        self.clock = clock

    @property
    def can_write(self) -> bool:
        return self.claude is not None

    @property
    def can_edit_photos(self) -> bool:
        return self.gemini is not None and bool(self.settings.gemini_image_model)

    def slots(self, month: date) -> list[Slot]:
        return month_slots(
            month,
            post_weekday=self.settings.content_post_weekday,
            story_every=self.settings.content_story_every_days,
        )

    # --- фото -----------------------------------------------------------------
    def add_photo(self, data: bytes, original_name: str = "") -> int:
        name, w, h = self.media.save_upload(data)
        with Session(self.engine) as s, s.begin():
            p = ContentPhoto(file=name, original_name=original_name[:200], width=w, height=h)
            s.add(p)
            s.flush()
            return p.id

    async def describe_photo(self, photo_id: int) -> None:
        with Session(self.engine) as s:
            p = s.get(ContentPhoto, photo_id)
            if p is None:
                return
            file = p.file
        img = base64.b64encode(self.media.for_ai(file)).decode()
        data, _, _ = await ask_json(
            self.claude, self.engine, self.settings, self.clock,
            model=self.settings.ai_model, effort="low",
            system="Ти описуєш фото салону краси для контент-плану. Українською, коротко.",
            content=[
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/jpeg", "data": img}},
                {"type": "text", "text": "Опиши фото 1–2 реченнями: що на ньому (яка послуга чи "
                 "результат, інтерʼєр, майстер за роботою), світло й настрій. category — тип "
                 "кадру; quality — чи придатне для соцмереж (різкість, світло)."},
            ],
            schema=PHOTO_SCHEMA, expect_out=300, kind="vision", est_in=1800,
        )  # fmt: skip
        desc = data.get("description", "").strip()
        if data.get("quality") == "poor":
            desc += " Якість слабка (світло або різкість)."
        with Session(self.engine) as s, s.begin():
            p = s.get(ContentPhoto, photo_id)
            if p is not None:
                p.description = desc
                p.category = data.get("category", "other")

    def delete_photo(self, photo_id: int) -> None:
        with Session(self.engine) as s, s.begin():
            p = s.get(ContentPhoto, photo_id)
            if p is None:
                return
            for it in s.scalars(select(ContentItem).where(ContentItem.photo_id == photo_id)):
                if it.status in ("ready", "published"):
                    raise ValueError("Фото вже в готовому пості — його не можна видалити")
                it.photo_id = None
                it.image_status = "none"
            self.media.delete(p.file)
            s.delete(p)

    def _library(self, s: Session) -> list[dict[str, Any]]:
        return [
            {"id": p.id, "category": p.category, "description": p.description or "без опису"}
            for p in s.scalars(select(ContentPhoto).order_by(ContentPhoto.id))
        ]

    # --- контекст для AI ------------------------------------------------------
    async def _services(self) -> list[dict[str, Any]]:
        if self.mds is not None:
            try:
                return _services_from_catalog(await self.mds.catalog())
            except Exception:  # noqa: BLE001
                return []
        return _services_local(self.engine)

    def _recent(self, s: Session, month: date) -> dict[str, Any]:
        since = month - timedelta(days=60)
        topics = [
            t
            for (t,) in s.execute(
                select(ContentItem.topic).where(
                    ContentItem.slot_date >= since, ContentItem.slot_date < month
                )
            )
        ]
        posts = [
            {"format": p.media_type, "caption_start": p.caption[:100], "reach": p.reach,
             "likes": p.likes, "saved": p.saved}
            for p in s.scalars(
                select(PostStat).where(PostStat.published_at >= self.clock() - timedelta(days=45))
                .order_by(PostStat.reach.desc()).limit(8)
            )
        ]  # fmt: skip
        return {"previous_topics": topics, "best_recent_posts": posts}

    def _ask(self, content: str, schema: dict[str, Any], expect_out: int, kind: str):  # noqa: ANN202
        return ask_json(
            self.claude, self.engine, self.settings, self.clock,
            model=self.settings.analyst_model, effort=self.settings.analyst_effort,
            system=SYSTEM, content=content, schema=schema, expect_out=expect_out, kind=kind,
        )  # fmt: skip

    @staticmethod
    def _apply(it: ContentItem, idea: dict[str, Any], library_ids: set[int]) -> None:
        it.topic = (idea.get("topic") or "")[:200]
        it.caption = idea.get("caption") or ""
        tags = [t.lstrip("#").strip() for t in idea.get("hashtags") or [] if t.strip()]
        it.hashtags = json.dumps(tags if it.kind == "post" else [], ensure_ascii=False)
        it.cta = (idea.get("cta") or "")[:300]
        pid = idea.get("photo_id") or 0
        it.photo_id = pid if pid in library_ids else None
        it.photo_note = "" if it.photo_id else (idea.get("photo_note") or "")
        it.edit_prompt = idea.get("edit_prompt") or ""
        it.status = "idea"
        it.image_file = None
        it.image_status = "none"
        it.image_rejections = 0
        it.image_feedback = ""

    # --- генерація місяця -----------------------------------------------------
    async def generate_month(self, month: date) -> int:
        """Заповнити ідеями вільні слоти місяця. Повертає кількість нових пунктів."""
        month = month.replace(day=1)
        with Session(self.engine) as s:
            taken = {
                (d, k)
                for d, k in s.execute(
                    select(ContentItem.slot_date, ContentItem.kind).where(
                        ContentItem.month == month
                    )
                )
            }
            library = self._library(s)
            recent = self._recent(s, month)
        free = [sl for sl in self.slots(month) if (sl.day, sl.kind) not in taken]
        if not free:
            return 0
        payload = {
            "month": f"{month:%Y-%m}",
            "slots": [
                {
                    "slot": i,
                    "date": sl.day.isoformat(),
                    "weekday": WD[sl.day.weekday()],
                    "kind": sl.kind,
                }
                for i, sl in enumerate(free)
            ],  # fmt: skip
            "photo_library": library,
            "services": await self._services(),
            **recent,
        }
        content = (
            "Наповни кожен слот контент-плану ідеєю (один елемент items на slot).\n"
            + json.dumps(payload, ensure_ascii=False, default=str)
        )
        data, _, _ = await self._ask(content, MONTH_SCHEMA, 450 * len(free), "plan")
        ids = {p["id"] for p in library}
        by_slot = {x.get("slot"): x for x in data.get("items") or []}
        n = 0
        with Session(self.engine) as s, s.begin():
            for i, sl in enumerate(free):
                idea = by_slot.get(i)
                if not idea:
                    continue
                it = ContentItem(month=month, slot_date=sl.day, kind=sl.kind, history="[]")
                self._apply(it, idea, ids)
                s.add(it)
                n += 1
        if n == 0:
            raise AiUnavailable("AI не запропонував жодної ідеї — спробуйте ще раз")
        return n

    # --- підтвердити / відхилити ідею -----------------------------------------
    def _get(self, s: Session, item_id: int) -> ContentItem:
        it = s.get(ContentItem, item_id)
        if it is None:
            raise ValueError("Пункт плану не знайдено")
        return it

    def approve(self, item_id: int) -> bool:
        """Підтвердити ідею. True — є фото, можна запускати обробку."""
        with Session(self.engine) as s, s.begin():
            it = self._get(s, item_id)
            if it.status != "idea":
                raise ValueError("Цю ідею вже підтверджено")
            it.status = "approved"
            return it.photo_id is not None

    def reject(self, item_id: int, reason: str = "") -> str:
        """Записати відхилення. Повертає 'variant' або 'new_topic' — що генерувати далі."""
        with Session(self.engine) as s, s.begin():
            it = self._get(s, item_id)
            if it.status != "idea":
                raise ValueError("Відхилити можна лише ідею, яку ще не підтвердили")
            hist = json.loads(it.history or "[]")
            hist.append({**_idea_dict(it), "reason": reason.strip()[:500],
                         "at": self.clock().isoformat(timespec="minutes")})  # fmt: skip
            it.history = json.dumps(hist, ensure_ascii=False)
            it.rejections += 1
            if it.rejections >= MAX_REJECTIONS:
                it.rejections = 0
                it.topics_tried += 1
                return "new_topic"
            return "variant"

    async def rework(self, item_id: int, mode: str) -> None:
        with Session(self.engine) as s:
            it = self._get(s, item_id)
            month = it.month
            hist = json.loads(it.history or "[]")
            slot = {"date": it.slot_date.isoformat(), "weekday": WD[it.slot_date.weekday()],
                    "kind": it.kind}  # fmt: skip
            others = [
                t for (t,) in s.execute(
                    select(ContentItem.topic).where(
                        ContentItem.month == month, ContentItem.id != item_id
                    )
                )
            ]  # fmt: skip
            library = self._library(s)
            recent = self._recent(s, month)
        if mode == "new_topic":
            task = (
                "Власник тричі відхилив цю тему. Придумай ПОВНІСТЮ НОВУ тему для слота — іншу "
                "за змістом, не схожу на відхилені й на інші теми місяця."
            )
            rejected = hist
        else:
            task = (
                "Власник відхилив ідею. Залиш ту саму тему, але помітно зміни подачу: інший "
                "кут, текст, заклик або фото. Обовʼязково врахуй причину відхилення."
            )
            rejected = hist[-MAX_REJECTIONS:]
        payload = {
            "slot": slot,
            "rejected_versions": rejected,
            "other_topics_this_month": others,
            "photo_library": library,
            "services": await self._services(),
            **recent,
        }
        content = task + "\n" + json.dumps(payload, ensure_ascii=False, default=str)
        idea, _, _ = await self._ask(content, IDEA_SCHEMA, 700, "plan")
        with Session(self.engine) as s, s.begin():
            it = self._get(s, item_id)
            self._apply(it, idea, {p["id"] for p in library})

    # --- фото до пункту -------------------------------------------------------
    def set_photo(self, item_id: int, photo_id: int) -> None:
        with Session(self.engine) as s, s.begin():
            it = self._get(s, item_id)
            if s.get(ContentPhoto, photo_id) is None:
                raise ValueError("Фото не знайдено")
            if it.status == "published":
                raise ValueError("Пост уже опубліковано")
            it.photo_id = photo_id
            it.photo_note = ""
            it.image_file = None
            it.image_status = "none"
            it.image_rejections = 0
            it.image_feedback = ""
            if it.status == "ready":
                it.status = "approved"

    async def edit_image(self, item_id: int) -> None:
        if not self.can_edit_photos:
            raise AiUnavailable("Обробка фото потребує GEMINI_API_KEY")
        with Session(self.engine) as s:
            it = self._get(s, item_id)
            if it.photo_id is None:
                raise ValueError("Спершу оберіть або завантажте фото")
            photo = s.get(ContentPhoto, it.photo_id)
            assert photo is not None
            file, kind = photo.file, it.kind
            prompt = STYLE.format(ratio=_ratio(kind)) + it.edit_prompt
            if it.image_feedback:
                prompt += " Owner's feedback on the previous edit (Ukrainian): " + it.image_feedback
        model = self.settings.gemini_image_model
        cost = prices.image_cost(model)
        with Session(self.engine) as s:
            budget.check(s, self.settings.ai_monthly_budget_usd, self.clock(),
                         self.settings.zone, cost)  # fmt: skip
        img = await self.gemini.image(
            model, prompt, aspect_ratio=_ratio(kind), source=self.media.read(file)
        )
        name = self.media.save_generated(img.data)
        with Session(self.engine) as s, s.begin():
            usage.record_units(s, provider="gemini", kind="image", model=model, units=1, cost=cost)
            it = self._get(s, item_id)
            if it.image_file:
                self.media.delete(it.image_file)
            it.image_file = name
            it.image_status = "ready"

    def approve_image(self, item_id: int) -> None:
        with Session(self.engine) as s, s.begin():
            it = self._get(s, item_id)
            if it.image_status != "ready":
                raise ValueError("Немає обробленого фото для підтвердження")
            it.image_status = "approved"
            if it.status == "approved":
                it.status = "ready"

    def use_original(self, item_id: int) -> None:
        """Опублікувати фото як є, без обробки AI."""
        with Session(self.engine) as s, s.begin():
            it = self._get(s, item_id)
            if it.status != "approved" or it.photo_id is None:
                raise ValueError("Спершу підтвердіть ідею й оберіть фото")
            if it.image_file:
                self.media.delete(it.image_file)
            it.image_file = None
            it.image_status = "approved"
            it.status = "ready"

    def reject_image(self, item_id: int, reason: str = "") -> str:
        """'retry' — переробити те саме фото; 'new_photo' — фото відʼєднано, потрібне інше."""
        with Session(self.engine) as s, s.begin():
            it = self._get(s, item_id)
            if it.image_status != "ready":
                raise ValueError("Немає обробленого фото")
            it.image_rejections += 1
            it.image_feedback = reason.strip()[:500]
            if it.image_rejections >= MAX_REJECTIONS:
                if it.image_file:
                    self.media.delete(it.image_file)
                it.image_file = None
                it.image_status = "none"
                it.image_rejections = 0
                it.image_feedback = ""
                it.photo_id = None
                it.photo_note = "Оберіть інше фото з бібліотеки або завантажте нове."
                return "new_photo"
            it.image_status = "none"
            return "retry"

    def mark_published(self, item_id: int) -> None:
        with Session(self.engine) as s, s.begin():
            it = self._get(s, item_id)
            if it.status != "ready":
                raise ValueError("Опублікувати можна лише готовий пункт")
            it.status = "published"

    def reset_month(self, month: date) -> int:
        """Прибрати непідтверджені ідеї місяця (щоб згенерувати заново)."""
        with Session(self.engine) as s, s.begin():
            r = s.execute(
                delete(ContentItem).where(
                    ContentItem.month == month.replace(day=1), ContentItem.status == "idea"
                )
            )
            return r.rowcount or 0

    # --- читання для сторінки -------------------------------------------------
    def items(self, month: date) -> list[ContentItem]:
        with Session(self.engine, expire_on_commit=False) as s:
            return list(
                s.scalars(
                    select(ContentItem)
                    .where(ContentItem.month == month.replace(day=1))
                    .order_by(ContentItem.slot_date, ContentItem.kind)
                )
            )

    def photos(self) -> list[ContentPhoto]:
        with Session(self.engine, expire_on_commit=False) as s:
            return list(s.scalars(select(ContentPhoto).order_by(ContentPhoto.id.desc())))
