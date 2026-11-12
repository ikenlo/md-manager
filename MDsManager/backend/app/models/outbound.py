from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import IdMixin, TimestampMixin, UTCDateTime, utcnow

OUTBOUND_STATUSES = ("pending", "sent", "failed")


class OutboundQueue(IdMixin, TimestampMixin, Base):
    """Черга відправки вихідних: воркер бере pending з next_retry_at <= now."""

    __tablename__ = "outbound_queue"

    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    next_retry_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", index=True
    )

    message: Mapped["Message"] = relationship()  # noqa: F821
