"""Ціни моделей для оцінки витрат. Перевіряйте актуальні на сайтах провайдерів.

Текст — $ за 1 млн токенів (вхід, вихід). Картинка — $ за штуку. Відео — $ за секунду.
Невідома модель → найдорожча ціна в групі (краще переоцінити, ніж пропустити бюджет).
"""

from __future__ import annotations

TEXT: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    # Gemini, платний тариф Standard (aistudio.google.com/docs/pricing, 11.2026)
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.8-flash": (0.75, 3.75),
}
# За одну картинку 1K
IMAGE: dict[str, float] = {
    "gemini-nano-banana-2.1": 0.0336,
    "gemini-3.1-flash-lite-image": 0.0336,
    "gemini-3.1-flash-image": 0.067,
    "gemini-3-pro-image": 0.134,
}
# Відео (Gemini Omni Flash, 720p) — ще не підключено; ціна для оцінок
VIDEO_PER_SECOND: dict[str, float] = {"gemini-omni-1.1-flash": 0.10}

CACHE_READ_MULT = 0.1
CACHE_WRITE_MULT = 1.25
UNKNOWN_IMAGE = 0.10
UNKNOWN_VIDEO_PER_SECOND = 0.75


def text_cost(model: str, inp: int, out: int, cache_read: int = 0, cache_write: int = 0) -> float:
    price_in, price_out = TEXT.get(model) or max(TEXT.values())
    return (
        inp * price_in
        + out * price_out
        + cache_read * price_in * CACHE_READ_MULT
        + cache_write * price_in * CACHE_WRITE_MULT
    ) / 1_000_000


def image_cost(model: str, count: int = 1) -> float:
    return IMAGE.get(model, UNKNOWN_IMAGE) * count


def video_cost(model: str, seconds: int) -> float:
    return VIDEO_PER_SECOND.get(model, UNKNOWN_VIDEO_PER_SECOND) * seconds
