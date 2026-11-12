from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import (
    CreatedMixin,
    IdMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UTCDateTime,
)

DIALOGUE_STATUSES = ("new", "in_progress", "ordered", "lost")
SENDER_TYPES = ("client", "agent", "human")


class Dialogue(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "dialogues"

    client_id: Mapped[int] = mapped_column(ForeignKey("crm_clients.id"), index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    assigned_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    last_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)

    client: Mapped["CrmClient"] = relationship()  # noqa: F821
    channel: Mapped["Channel"] = relationship()  # noqa: F821
    assigned_agent: Mapped["Agent | None"] = relationship()  # noqa: F821
    messages: Mapped[list["Message"]] = relationship(
        back_populates="dialogue",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.id",
    )
    tags: Mapped[list["DialogTag"]] = relationship(
        back_populates="dialogue", cascade="all, delete-orphan", passive_deletes=True
    )


class Message(IdMixin, CreatedMixin, Base):
    __tablename__ = "messages"

    dialogue_id: Mapped[int] = mapped_column(
        ForeignKey("dialogues.id", ondelete="CASCADE"), index=True
    )
    sender_type: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)

    dialogue: Mapped[Dialogue] = relationship(back_populates="messages")


class DialogTag(IdMixin, TimestampMixin, Base):
    __tablename__ = "dialog_tags"

    dialogue_id: Mapped[int] = mapped_column(
        ForeignKey("dialogues.id", ondelete="CASCADE"), index=True
    )
    tag_name: Mapped[str] = mapped_column(String(64))

    dialogue: Mapped[Dialogue] = relationship(back_populates="tags")
