"""Клієнт Gemini API (ai.google.dev) через REST — без окремого SDK.

Використовується для дешевої масової генерації: варіанти текстів, картинки.
Аналіз і рішення лишаються за Claude.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta"


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
        self.http = http or httpx.AsyncClient(timeout=120)

    async def _generate(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            r = await self.http.post(
                f"{BASE}/models/{model}:generateContent",
                headers={"x-goog-api-key": self.api_key},
                json=body,
            )
        except httpx.HTTPError as e:
            raise GeminiError(503, "Gemini недоступний") from e
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", "")
            except ValueError:
                msg = ""
            raise GeminiError(r.status_code, msg or f"Gemini: помилка {r.status_code}")
        return r.json()

    @staticmethod
    def _parts(data: dict[str, Any]) -> list[dict[str, Any]]:
        cands = data.get("candidates") or []
        if not cands:
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise GeminiError(422, f"Gemini не відповів ({reason or 'порожня відповідь'})")
        return (cands[0].get("content") or {}).get("parts") or []

    async def text(self, model: str, prompt: str, *, max_output_tokens: int = 4096) -> TextResult:
        data = await self._generate(
            model,
            {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_output_tokens},
            },
        )
        text = "".join(p.get("text", "") for p in self._parts(data)).strip()
        if not text:
            raise GeminiError(422, "Gemini повернув порожній текст")
        meta = data.get("usageMetadata") or {}
        return TextResult(
            text,
            int(meta.get("promptTokenCount") or 0),
            # thinking-токени теж оплачуються як вихідні
            int(meta.get("candidatesTokenCount") or 0) + int(meta.get("thoughtsTokenCount") or 0),
        )

    async def image(self, model: str, prompt: str) -> ImageResult:
        data = await self._generate(
            model,
            {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
            },
        )
        caption = ""
        for p in self._parts(data):
            inline = p.get("inlineData") or p.get("inline_data")
            if inline and inline.get("data"):
                return ImageResult(
                    base64.b64decode(inline["data"]),
                    inline.get("mimeType") or inline.get("mime_type") or "image/png",
                    caption,
                )
            caption += p.get("text", "")
        raise GeminiError(422, "Gemini не повернув картинку")
