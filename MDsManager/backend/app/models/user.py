from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import IdMixin, SoftDeleteMixin, TimestampMixin


class User(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(32), default="director")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    sessions: Mapped[list["UserSession"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
