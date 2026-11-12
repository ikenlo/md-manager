"""Локальне сховище вкладень (MEDIA_DIR/<dialogue_uuid>/<asset_uuid>.<ext>)."""

from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Dialogue, MediaAsset, Message
from app.models.base import new_uuid


def media_root() -> Path:
    return Path(get_settings().media_dir).resolve()


def asset_url(asset: MediaAsset) -> str:
    return f"/api/media/{asset.uuid}"


def save_asset(
    db: Session,
    dialogue: Dialogue,
    message: Message | None,
    data: bytes,
    mime_type: str,
    ext: str,
    meta_url: str | None = None,
) -> MediaAsset:
    """Записує файл і додає MediaAsset у сесію (commit — на викликачеві)."""
    uuid = new_uuid()
    rel = Path(dialogue.uuid) / f"{uuid}.{ext}"
    path = media_root() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    asset = MediaAsset(
        uuid=uuid,
        dialogue_id=dialogue.id,
        message_id=message.id if message else None,
        file_path=rel.as_posix(),
        mime_type=mime_type,
        file_size=len(data),
        meta_url=meta_url,
    )
    db.add(asset)
    return asset


def resolve_asset_path(asset: MediaAsset) -> Path | None:
    """Абсолютний шлях, лише якщо він усередині MEDIA_DIR і файл існує."""
    root = media_root()
    path = (root / asset.file_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path
