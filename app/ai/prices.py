"""Ціни моделей для оцінки витрат. Перевіряйте актуальні на сайтах провайдерів.

Текст — $ за 1 млн токенів (вхід, вихід). Картинка — $ за штуку. Відео — $ за секунду.
Невідома модель → найдорожча ціна в групі (краще переоцінити, ніж пропустити бюджет).
"""

from __future__ import annotations

TEXT: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
IMAGE: dict[str, float] = {}
VIDEO_PER_SECOND: dict[str, float] = {}

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
