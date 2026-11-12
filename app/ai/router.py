"""Маршрутизатор моделей: дешеві масові задачі — Gemini, аналіз і діалоги — Claude.

Кожен виклик проходить перевірку місячного бюджету і записується в ai_usage з ціною.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.agent import usage
from app.ai import budget, prices
from app.ai.gemini import GeminiClient, ImageResult
from app.config import Settings

CLAUDE_FALLBACK_MODEL = "claude-haiku-5-5"

COPYWRITER = (
    "Ти — копірайтер салону краси M&D (Київська область). Пиши українською, тепло, "
    "на «ви», без канцеляриту й без вигаданих цін чи акцій. Результат — готовий до "
    "публікації текст, без вступів і пояснень.\n\nЗАВДАННЯ:\n"
)


class AiUnavailable(Exception):
    pass


@dataclass
class TextOut:
    text: str
    provider: str
    model: str
    cost_usd: float


class AiRouter:
    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        *,
        gemini: GeminiClient | None = None,
        claude: Any = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.gemini = gemini
        self.claude = claude
        self.clock = clock

    def _check(self, upcoming: float) -> None:
        with Session(self.engine) as s:
            budget.check(
                s, self.settings.ai_monthly_budget_usd, self.clock(), self.settings.zone, upcoming
            )

    async def bulk_text(self, task: str, *, max_output_tokens: int = 4096) -> TextOut:
        """Масові тексти (варіанти підписів, оголошень, хештеги): Gemini, інакше Claude Haiku."""
        prompt = COPYWRITER + task
        est_in = len(prompt) // 2  # грубо: кирилиця ≈ 2 символи на токен
        if self.gemini and self.settings.gemini_text_model:
            model = self.settings.gemini_text_model
            self._check(prices.text_cost(model, est_in, max_output_tokens))
            r = await self.gemini.text(model, prompt, max_output_tokens=max_output_tokens)
            u = type("U", (), {"input_tokens": r.input_tokens, "output_tokens": r.output_tokens})
            with Session(self.engine) as s, s.begin():
                row = usage.record(s, None, model, u, provider="gemini", kind="text")
                cost = row.cost_usd
            return TextOut(r.text, "gemini", model, cost)
        if self.claude is None:
            raise AiUnavailable(
                "Немає ні Gemini, ні Claude — задайте GEMINI_API_KEY або ANTHROPIC_API_KEY"
            )
        model = CLAUDE_FALLBACK_MODEL
        self._check(prices.text_cost(model, est_in, max_output_tokens))
        resp = await self.claude.messages.create(
            model=model,
            max_tokens=max_output_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low"},
        )
        text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
        with Session(self.engine) as s, s.begin():
            row = usage.record(s, None, model, resp.usage, provider="anthropic", kind="text")
            cost = row.cost_usd
        return TextOut(text, "anthropic", model, cost)

    async def image(self, description: str) -> tuple[ImageResult, float]:
        if not (self.gemini and self.settings.gemini_image_model):
            raise AiUnavailable("Генерація картинок не налаштована (GEMINI_IMAGE_MODEL)")
        model = self.settings.gemini_image_model
        cost = prices.image_cost(model)
        self._check(cost)
        img = await self.gemini.image(
            model,
            "Фото для соцмереж салону краси M&D, реалістично, без тексту на зображенні, "
            "без логотипів інших брендів. " + description,
        )
        with Session(self.engine) as s, s.begin():
            usage.record_units(s, provider="gemini", kind="image", model=model, units=1, cost=cost)
        return img, cost
