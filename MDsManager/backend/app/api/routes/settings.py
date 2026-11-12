from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.database import get_db
from app.models import User
from app.schemas.settings import SettingIn, SettingOut
from app.services import settings_store

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.post("", response_model=SettingOut)
def save_setting(
    body: SettingIn, db: Session = Depends(get_db), _: User = Depends(current_user)
) -> SettingOut:
    row = settings_store.upsert_setting(db, body.key, body.value, body.is_secret)
    return SettingOut(
        key=row.key, value=None if row.is_secret else body.value, is_secret=row.is_secret
    )


@router.get("", response_model=list[SettingOut])
def get_settings_list(
    db: Session = Depends(get_db), _: User = Depends(current_user)
) -> list[SettingOut]:
    return [
        SettingOut(key=r.key, value=v, is_secret=r.is_secret)
        for r, v in settings_store.list_settings(db)
    ]
