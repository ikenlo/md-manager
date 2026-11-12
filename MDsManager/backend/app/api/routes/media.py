from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MediaAsset
from app.services.media import resolve_asset_path

router = APIRouter(prefix="/api/media", tags=["media"])


@router.get(
    "/{uuid}",
    summary="Файл вкладення",
    description=(
        "Без Bearer: `<img src>` не надсилає заголовків. Доступ — за знанням UUID (uuid4, "
        "неперебірний), як у посиланнях CDN Meta."
    ),
)
def get_media(uuid: str, db: Session = Depends(get_db)) -> FileResponse:
    asset = db.scalar(select(MediaAsset).where(MediaAsset.uuid == uuid))
    path = resolve_asset_path(asset) if asset else None
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не знайдено")
    return FileResponse(
        path,
        media_type=asset.mime_type,
        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )
