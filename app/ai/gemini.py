"""Клієнт Gemini API через REST (Interactions API — основний інтерфейс Google з 06.2026).

POST https://generativelanguage.googleapis.com/v1beta/interactions
Відповідь: steps[] → крок type="model_output" → content[] з блоками type="text" | "image".
Використовується для дешевої масової генерації; аналіз і рішення лишаються за Claude.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import httpx

URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
API_REVISION = "2026-05-20"


class GeminiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class TextResult:
    text: str
    input_tokens: int
    output_tokens: int


@dataclass
class ImageResult:
    data: bytes
    mime_type: str
    caption: str


class GeminiClient:
    def __init__(self, api_key: str, http: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key
        self.http = http or httpx.AsyncClient(timeout=180)

    async def _interact(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            r = await self.http.post(
                URL,
                headers={"x-goog-api-key": self.api_key, "Api-Revision": API_REVISION},
                # store=false: Google не зберігає взаємодію (дані клієнтів салону)
                json={**body, "store": False},
            )
        except httpx.HTTPError as e:
            raise GeminiError(503, "Gemini недоступний") from e
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", "")
            except ValueError:
                msg = ""
            raise GeminiError(r.status_code, msg or f"Gemini: помилка {r.status_code}")
        data = r.json()
        if data.get("status") not in (None, "completed"):
            raise GeminiError(422, f"Gemini: статус {data.get('status')}")
        return data

    @staticmethod
    def _blocks(data: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for step in data.get("steps") or []:
            if step.get("type") == "model_output":
                out.extend(step.get("content") or [])
        if not out:
            raise GeminiError(422, "Gemini повернув порожню відповідь")
        return out

    @staticmethod
    def _usage(data: dict[str, Any]) -> tuple[int, int]:
        u = data.get("usage") or {}
        inp = int(u.get("total_input_tokens") or 0)
        # «роздуми» моделі оплачуються як вихідні токени
        out = int(u.get("total_output_tokens") or 0) + int(u.get("total_thought_tokens") or 0)
        return inp, out

    async def text(self, model: str, prompt: str, *, max_output_tokens: int = 4096) -> TextResult:
        data = await self._interact(
            {
                "model": model,
                "input": prompt,
                "generation_config": {"max_output_tokens": max_output_tokens},
            }
        )
        text = "".join(b.get("text", "") for b in self._blocks(data) if b.get("type") == "text")
        if not text.strip():
            raise GeminiError(422, "Gemini повернув порожній текст")
        inp, out = self._usage(data)
        return TextResult(text.strip(), inp, out)

    async def image(
        self, model: str, prompt: str, *, aspect_ratio: str = "4:5", image_size: str = "1K"
    ) -> ImageResult:
        data = await self._interact(
            {
                "model": model,
                "input": prompt,
                "response_format": {
                    "type": "image",
                    "mime_type": "image/jpeg",
                    "aspect_ratio": aspect_ratio,
                    "image_size": image_size,  # лише з великою K: "1K", "2K", "4K"
                },
            }
        )
        caption = ""
        for b in self._blocks(data):
            if b.get("type") == "image" and b.get("data"):
                return ImageResult(
                    base64.b64decode(b["data"]), b.get("mime_type") or "image/jpeg", caption
                )
            caption += b.get("text", "")
        raise GeminiError(422, "Gemini не повернув картинку")
