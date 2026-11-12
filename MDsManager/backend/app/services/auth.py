import hashlib
import secrets
from datetime import timedelta

import bcrypt
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User, UserSession
from app.models.base import utcnow


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(
        select(User).where(User.email == email.lower().strip(), User.deleted_at.is_(None))
    )
    if user is None or not user.is_active:
        # вирівнюємо час відповіді
        bcrypt.checkpw(b"x", bcrypt.hashpw(b"y", bcrypt.gensalt(4)))
        return None
    return user if verify_password(password, user.password_hash) else None


def create_session(
    db: Session, user: User, ip: str | None, user_agent: str | None
) -> tuple[str, UserSession]:
    token = secrets.token_urlsafe(48)
    sess = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(days=get_settings().session_ttl_days),
        ip_address=ip,
        user_agent=(user_agent or "")[:512] or None,
    )
    db.add(sess)
    db.execute(delete(UserSession).where(UserSession.expires_at < utcnow()))
    db.commit()
    return token, sess


def user_by_token(db: Session, token: str) -> User | None:
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if sess is None or sess.expires_at <= utcnow():
        return None
    user = sess.user
    if not user.is_active or user.deleted_at is not None:
        return None
    return user


def revoke_session(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
    db.commit()
