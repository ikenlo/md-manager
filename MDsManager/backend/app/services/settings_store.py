from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Setting
from app.services.crypto import decrypt, encrypt


def upsert_setting(db: Session, key: str, value: str, is_secret: bool) -> Setting:
    row = db.scalar(select(Setting).where(Setting.key == key))
    if row is None:
        row = Setting(key=key, value_encrypted="", is_secret=is_secret)
        db.add(row)
    row.value_encrypted = encrypt(value)
    row.is_secret = is_secret
    db.commit()
    return row


def get_setting(db: Session, key: str) -> str | None:
    row = db.scalar(select(Setting).where(Setting.key == key))
    return decrypt(row.value_encrypted) if row else None


def list_settings(db: Session) -> list[tuple[Setting, str | None]]:
    rows = db.scalars(select(Setting).order_by(Setting.key)).all()
    return [(r, None if r.is_secret else decrypt(r.value_encrypted)) for r in rows]
