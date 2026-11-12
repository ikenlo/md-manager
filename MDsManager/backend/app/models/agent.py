from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import IdMixin, SoftDeleteMixin, TimestampMixin

AGENT_ROLES = ("sales", "support")


class Agent(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(32), default="sales")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
