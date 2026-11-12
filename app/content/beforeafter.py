"""Фото «до / після». Підписи фірмовим шрифтом накладає код, а не AI: генератори пишуть з помилками.

compose(before, after) — два фото в одне 4:5, однакова висота й кадр, тонка світла лінія посередині.
label(img, split_x) — підписи «ДО» і «ПІСЛЯ» на готовій картинці (наприклад, після обробки Gemini).
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

FONT = Path(__file__).resolve().parents[1] / "web" / "static" / "fonts" / "cormorant-cyr.woff2"
GOLD = (210, 171, 95)
GREEN = (20, 57, 44)
SIZE = (1080, 1350)  # 4:5 для Instagram


def _font(px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        f = ImageFont.truetype(str(FONT), px)
        try:
            f.set_variation_by_axes([600])  # напівжирний, як заголовки MDS
        except (OSError, ValueError):
            pass
        return f
    except OSError:
        return ImageFont.load_default()


def _tag(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, px: int) -> None:
    font = _font(px)
    x, y = xy
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    pad_x, pad_y = int(px * 0.55), int(px * 0.3)
    w, h = right - left + 2 * pad_x, bottom - top + 2 * pad_y
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=(*GREEN, 205))
    draw.text((x + pad_x - left, y + pad_y - top), text, font=font, fill=GOLD)


def label(img: Image.Image, split_x: int | None = None) -> Image.Image:
    """Підписи «ДО» і «ПІСЛЯ». split_x — де лінія поділу (за замовчуванням посередині)."""
    out = img.convert("RGBA")
    w, h = out.size
    split_x = split_x or w // 2
    layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    px = max(22, w // 22)
    m = max(14, w // 40)
    _tag(d, (m, m), "ДО", px)
    _tag(d, (split_x + m, m), "ПІСЛЯ", px)
    mark = _font(max(14, w // 48))
    d.text((w - m, h - m), "M&D", font=mark, fill=(*GOLD, 230), anchor="rd")
    return Image.alpha_composite(out, layer).convert("RGB")


def compose(before: bytes, after: bytes, size: tuple[int, int] = SIZE, gap: int = 6) -> bytes:
    """Звести два фото в одне: кожна половина — центральний кадр однакового розміру."""
    w, h = size
    half = (w - gap) // 2
    canvas = Image.new("RGB", size, (245, 241, 230))
    for i, data in enumerate((before, after)):
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        img = ImageOps.fit(img, (half, h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.4))
        canvas.paste(img, (0 if i == 0 else half + gap, 0))
    buf = io.BytesIO()
    label(canvas, half + gap).save(buf, "JPEG", quality=92)
    return buf.getvalue()
