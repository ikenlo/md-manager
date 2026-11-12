"""Сторіс з текстом (1080×1920): фон — фото салону (розмите й притемнене) або фірмовий зелений,
текст накладає код фірмовими шрифтами MDS — без помилок, які роблять генератори картинок.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

FONTS = Path(__file__).resolve().parents[1] / "web" / "static" / "fonts"
SIZE = (1080, 1920)
GREEN = (20, 57, 44)
GOLD = (210, 171, 95)
CREAM = (245, 241, 230)


@dataclass
class Story:
    kicker: str  # дрібний рядок над заголовком
    title: str  # великий заголовок (можна з \n)
    lines: list[str] = field(default_factory=list)  # 1–3 рядки під заголовком
    ways: list[tuple[str, str]] = field(default_factory=list)  # (як записатись, деталь)
    footer: str = ""  # підказка біля місця для наліпки


class Font:
    """Шрифти MDS поділені на кирилицю (-cyr) і латиницю з цифрами (-lat) — беремо обидва."""

    def __init__(self, family: str, px: int, weight: int) -> None:
        self.cyr = self._load(f"{family}-cyr.woff2", px, weight)
        self.lat = self._load(f"{family}-lat.woff2", px, weight)

    @staticmethod
    def _load(name: str, px: int, weight: int) -> ImageFont.FreeTypeFont:
        f = ImageFont.truetype(str(FONTS / name), px)
        try:
            f.set_variation_by_axes([weight])
        except (OSError, ValueError):
            pass
        return f

    def runs(self, text: str) -> list[tuple[str, ImageFont.FreeTypeFont]]:
        out: list[tuple[str, ImageFont.FreeTypeFont]] = []
        for ch in text:
            f = self.cyr if 0x0400 <= ord(ch) <= 0x04FF or ord(ch) == 0x2116 else self.lat
            if out and out[-1][1] is f:
                out[-1] = (out[-1][0] + ch, f)
            else:
                out.append((ch, f))
        return out

    def length(self, draw: ImageDraw.ImageDraw, text: str) -> float:
        return sum(draw.textlength(t, font=f) for t, f in self.runs(text))


def _text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font: Font,
          fill: tuple[int, ...], anchor: str = "la") -> None:  # fmt: skip
    """anchor: l/m — по горизонталі (ліво / центр), a/t/m — по вертикалі, як у Pillow."""
    x, y = xy
    if anchor[0] == "m":
        x -= font.length(draw, text) / 2
    # одна базова лінія для всіх шматків, інакше слова без виносних «стрибають»
    ascent, descent = font.cyr.getmetrics()
    base = y + (ascent - descent) / 2 if anchor[1] == "m" else y + ascent
    for t, f in font.runs(text):
        draw.text((x, base), t, font=f, fill=fill, anchor="ls")
        x += draw.textlength(t, font=f)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Font, width: int) -> list[str]:
    out: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            test = f"{line} {word}".strip()
            if font.length(draw, test) <= width or not line:
                line = test
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


def _background(photo: bytes | None) -> Image.Image:
    if photo is None:
        return Image.new("RGB", SIZE, GREEN)
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(photo))).convert("RGB")
    img = ImageOps.fit(img, SIZE, method=Image.Resampling.LANCZOS).filter(
        ImageFilter.GaussianBlur(14)
    )
    shade = Image.new("RGB", SIZE, GREEN)
    return Image.blend(img, shade, 0.62)


def render(story: Story, photo: bytes | None = None) -> bytes:
    img = _background(photo).convert("RGBA")
    layer = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w, _ = SIZE
    m = 96
    y = 250

    mark = Font("cormorant", 44, 600)
    _text(d, (w // 2, 150), "M&D", mark, GOLD, "mm")

    kicker = Font("manrope", 34, 600)
    _text(d, (w // 2, y), story.kicker.upper(), kicker, GOLD, "mm")
    y += 70

    title = Font("cormorant", 118, 600)
    for line in _wrap(d, story.title, title, w - 2 * m):
        _text(d, (w // 2, y), line, title, CREAM, "mt")
        y += 124
    y += 60
    d.line((w // 2 - 70, y, w // 2 + 70, y), fill=GOLD, width=3)
    y += 50

    body = Font("manrope", 42, 500)
    for text in story.lines:
        for line in _wrap(d, text, body, w - 2 * m):
            _text(d, (w // 2, y), line, body, CREAM, "mt")
            y += 58
    y += 50

    if story.ways:
        label = Font("manrope", 30, 700)
        name = Font("manrope", 40, 600)
        detail = Font("manrope", 32, 500)
        box_h = 116
        top = y
        bottom = top + len(story.ways) * box_h + 96
        d.rounded_rectangle((m - 20, top, w - m + 20, bottom), radius=36,
                            fill=(245, 241, 230, 26), outline=(*GOLD, 140), width=2)  # fmt: skip
        _text(d, (w // 2, top + 34), "ЯК ЗАПИСАТИСЯ", label, GOLD, "mm")
        yy = top + 80
        for i, (way, extra) in enumerate(story.ways, 1):
            cx = m + 40
            d.ellipse((cx - 26, yy + 8, cx + 26, yy + 60), outline=GOLD, width=3)
            _text(d, (cx, yy + 34), str(i), label, GOLD, "mm")
            _text(d, (cx + 52, yy + 2), way, name, CREAM)
            if extra:
                _text(d, (cx + 52, yy + 52), extra, detail, (*CREAM, 190))
            yy += box_h
        y = bottom

    if story.footer:
        foot = Font("manrope", 30, 500)
        _text(d, (w // 2, SIZE[1] - 330), story.footer, foot, (*CREAM, 170), "mm")

    out = Image.alpha_composite(img, layer).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=92)
    return buf.getvalue()
