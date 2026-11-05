"""Тип колонки для часу: у БД завжди UTC, у Python — aware datetime (UTC)."""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Зберігає datetime як UTC.

    SQLite не має timestamptz, тому пишемо naive-UTC і на читанні
    повертаємо aware-UTC. У Postgres колонка буде timestamptz.
    Naive datetime на вході — помилка: час без зони плутає «завтра».
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime заборонено: передайте aware datetime")
        value = value.astimezone(UTC)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)
