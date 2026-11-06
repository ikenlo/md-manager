"""Файли фото: нормалізація (поворот за EXIF, без метаданих і геолокації), мініатюри."""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_SIDE = 2048
THUMB_SIDE = 480
AI_SIDE = 1024  # для опису фото — дешевше
ALLOWED = {"JPEG", "PNG", "WEBP", "MPO"}


class PhotoError(ValueError):
    pass


class Media:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path(self, name: str) -> Path:
        if "/" in name or "\\" in name or name.startswith("."):
            raise PhotoError("Некоректне імʼя файлу")
        return self.root / name

    def thumb_path(self, name: str) -> Path:
        return self.path("t_" + name)

    def _save(self, img: Image.Image, prefix: str) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        name = f"{prefix}{uuid.uuid4().hex}.jpg"
        img.save(self.path(name), "JPEG", quality=90, optimize=True)
        thumb = img.copy()
        thumb.thumbnail((THUMB_SIDE, THUMB_SIDE))
        thumb.save(self.thumb_path(name), "JPEG", quality=82)
        return name

    def save_upload(self, data: bytes) -> tuple[str, int, int]:
        """Зберегти завантажене фото → (імʼя файлу, ширина, висота)."""
        if len(data) > MAX_UPLOAD_BYTES:
            raise PhotoError("Фото більше 20 МБ — зменште його або надішліть інше")
        try:
            img = Image.open(io.BytesIO(data))
            fmt = img.format
            img.load()
        except (UnidentifiedImageError, OSError) as e:
            raise PhotoError("Це не фото (потрібен JPEG, PNG або WEBP)") from e
        if fmt not in ALLOWED:
            raise PhotoError(f"Формат {fmt} не підтримується — потрібен JPEG, PNG або WEBP")
        img = ImageOps.exif_transpose(img).convert("RGB")  # без EXIF: зникає й геолокація
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        return self._save(img, "p_"), img.width, img.height

    def save_generated(self, data: bytes) -> str:
        try:
            img = Image.open(io.BytesIO(data)).convert("RGB")
        except (UnidentifiedImageError, OSError) as e:
            raise PhotoError("Генератор повернув пошкоджене фото") from e
        return self._save(img, "e_")

    def read(self, name: str) -> bytes:
        return self.path(name).read_bytes()

    def for_ai(self, name: str) -> bytes:
        img = Image.open(self.path(name))
        img.thumbnail((AI_SIDE, AI_SIDE))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        return buf.getvalue()

    def delete(self, name: str) -> None:
        for p in (self.path(name), self.thumb_path(name)):
            p.unlink(missing_ok=True)
