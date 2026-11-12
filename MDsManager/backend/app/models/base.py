import uuid as uuid_lib
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Зберігає UTC; naive datetime на вході — помилка; на виході — aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime заборонено — передайте aware UTC")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect):
        return None if value is None else value.replace(tzinfo=UTC)


def new_uuid() -> str:
    return str(uuid_lib.uuid4())


class IdMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid)


class CreatedMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class TimestampMixin(CreatedMixin):
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
