from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import CreatedMixin, IdMixin, UTCDateTime

AI_INTENTS = ("booking", "question", "escalate", "unknown")
SUGGESTION_STATUSES = ("pending", "approved", "rejected", "expired")


class AISuggestion(IdMixin, CreatedMixin, Base):
    """Відповідь AI, що чекає рішення адміністратора (human-in-the-loop).

    approve → текст іде клієнту, proposed_booking виконується; reject / expired — ні.
    """

    __tablename__ = "ai_suggestions"

    dialogue_id: Mapped[int] = mapped_column(
        ForeignKey("dialogues.id", ondelete="CASCADE"), index=True
    )
    # повідомлення клієнта, на яке відповідав AI
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    content: Mapped[str] = mapped_column(Text)
    # {"tool", "service_name", "date", "time", "arguments"} або None
    proposed_booking: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    intent: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    dialogue: Mapped["Dialogue"] = relationship(back_populates="ai_suggestions")  # noqa: F821
