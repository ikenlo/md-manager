"""SQLAlchemy-моделі. Усі часи — UTC (див. UTCDateTime)."""

from __future__ import annotations

import enum
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.db.types import UTCDateTime, utcnow


class Base(DeclarativeBase):
    pass


class BookingStatus(enum.StrEnum):
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


class Channel(enum.StrEnum):
    instagram = "instagram"
    telegram = "telegram"
    admin = "admin"


class ConversationState(enum.StrEnum):
    ai = "ai"
    paused = "paused"
    closed = "closed"


class MessageRole(enum.StrEnum):
    client = "client"
    assistant = "assistant"
    admin = "admin"


def _enum(e: type[enum.Enum], name: str) -> Enum:
    # native_enum=False → VARCHAR + CHECK, однаково в SQLite і Postgres
    return Enum(e, name=name, native_enum=False, validate_strings=True, length=20)


class SalonSetting(Base):
    __tablename__ = "salon_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    tg_user_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    services: Mapped[list[Service]] = relationship(
        secondary="master_services", back_populates="masters"
    )
    schedule: Mapped[list[WorkSchedule]] = relationship(
        back_populates="master", cascade="all, delete-orphan"
    )
    exceptions: Mapped[list[ScheduleException]] = relationship(
        back_populates="master", cascade="all, delete-orphan"
    )


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100), default="")
    price_from: Mapped[int] = mapped_column(Integer)  # грн
    price_to: Mapped[int | None] = mapped_column(Integer)
    duration_min: Mapped[int] = mapped_column(Integer)
    buffer_min: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    masters: Mapped[list[Master]] = relationship(
        secondary="master_services", back_populates="services"
    )


class MasterService(Base):
    __tablename__ = "master_services"

    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="CASCADE"), primary_key=True
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), primary_key=True
    )


class WorkSchedule(Base):
    """Звичайний тиждень. weekday: 0 = понеділок … 6 = неділя. Час — київський."""

    __tablename__ = "work_schedule"
    __table_args__ = (UniqueConstraint("master_id", "weekday", "start_time"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    master: Mapped[Master] = relationship(back_populates="schedule")


class ScheduleException(Base):
    """Лікарняні, відпустки, зміни графіка на конкретну дату (київський час)."""

    __tablename__ = "schedule_exceptions"
    __table_args__ = (UniqueConstraint("master_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    is_day_off: Mapped[bool] = mapped_column(Boolean, default=False)

    master: Mapped[Master] = relationship(back_populates="exceptions")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    ig_user_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    tg_user_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    bookings: Mapped[list[Booking]] = relationship(back_populates="client")


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        Index("ix_bookings_master_start", "master_id", "start_at"),
        Index("ix_bookings_status_start", "status", "start_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"))
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    start_at: Mapped[datetime] = mapped_column(UTCDateTime)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime)  # без буфера
    status: Mapped[BookingStatus] = mapped_column(
        _enum(BookingStatus, "booking_status"), default=BookingStatus.confirmed
    )
    source: Mapped[Channel] = mapped_column(_enum(Channel, "booking_source"))
    reminded_24h: Mapped[bool] = mapped_column(Boolean, default=False)
    reminded_2h: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(64), default="")  # "ai" / tg_user_id адміна
    lead_source: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    client: Mapped[Client] = relationship(back_populates="bookings")
    master: Mapped[Master] = relationship()
    service: Mapped[Service] = relationship()


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("channel", "client_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[Channel] = mapped_column(_enum(Channel, "conversation_channel"))
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    state: Mapped[ConversationState] = mapped_column(
        _enum(ConversationState, "conversation_state"), default=ConversationState.ai
    )
    last_inbound_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    lead_source: Mapped[str | None] = mapped_column(String(64))  # мітка посилання / реклами
    paused_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    client: Mapped[Client] = relationship()
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(_enum(MessageRole, "message_role"))
    text: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(128), index=True)  # mid з Meta
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class AiUsage(Base):
    """Токени кожного виклику Claude — для /stats і контролю витрат."""

    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(16), default="anthropic")  # anthropic | gemini
    kind: Mapped[str] = mapped_column(String(16), default="chat")  # chat | text | image | video
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    units: Mapped[int] = mapped_column(Integer, default=0)  # картинки або секунди відео
    cost_usd: Mapped[float] = mapped_column(
        Float, default=0.0
    )  # оцінка за прайсом на момент виклику
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class MetricDaily(Base):
    """Щоденна метрика з зовнішнього джерела (Instagram, Facebook, Google, TikTok)."""

    __tablename__ = "metric_daily"
    __table_args__ = (UniqueConstraint("day", "source", "metric"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)  # київська дата
    source: Mapped[str] = mapped_column(String(32))  # instagram | facebook | google | tiktok
    metric: Mapped[str] = mapped_column(String(64))  # reach, views, profile_links_taps, ...
    value: Mapped[float] = mapped_column(Float, default=0.0)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AdDaily(Base):
    """Результати оголошення за день (Meta Ads). Гроші — у валюті рекламного акаунта, копійки."""

    __tablename__ = "ad_daily"
    __table_args__ = (UniqueConstraint("day", "platform", "ad_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    platform: Mapped[str] = mapped_column(String(16), default="meta")
    ad_id: Mapped[str] = mapped_column(String(64))
    ad_name: Mapped[str] = mapped_column(String(200), default="")
    campaign_name: Mapped[str] = mapped_column(String(200), default="")
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    spend_minor: Mapped[int] = mapped_column(Integer, default=0)
    conversations: Mapped[int] = mapped_column(Integer, default=0)  # розпочаті діалоги в Direct
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
