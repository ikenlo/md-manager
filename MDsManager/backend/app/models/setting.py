from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import IdMixin, TimestampMixin


class Setting(IdMixin, TimestampMixin, Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), unique=True)
    value_encrypted: Mapped[str] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
