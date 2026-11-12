from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

DialogueStatus = Literal["new", "in_progress", "ordered", "lost"]
ChannelType = Literal["instagram", "facebook", "telegram"]
SenderType = Literal["client", "agent", "human"]


class ClientOut(BaseModel):
    uuid: str
    name: str
    instagram_handle: str | None
    phone: str | None


class ChannelOut(BaseModel):
    uuid: str
    channel_type: str
    account_name: str


class MessageOut(BaseModel):
    id: int
    uuid: str
    sender_type: str
    content: str
    direction: str
    status: str
    attachments: list[dict[str, Any]] | None = None
    created_at: datetime


class DialogueOut(BaseModel):
    uuid: str
    status: str
    last_message_at: datetime | None
    client: ClientOut
    channel: ChannelOut
    tags: list[str]
    last_message: MessageOut | None
    unread_count: int
    last_inbound_at: datetime | None
    # стан підключення каналу: active | error | expired | inactive
    webhook_status: str
    # діалог веде AI-агент (assigned_agent); перемикання — Фаза 3
    ai_active: bool


class DialogueList(BaseModel):
    items: list[DialogueOut]
    total: int


class MessageCreateRequest(BaseModel):
    """Повідомлення від оператора. `content` — стара назва поля (Фаза 1), приймається теж."""

    model_config = ConfigDict(extra="forbid")

    # порожній / з пробілів → 400 у роутері (не 422), тож min_length тут немає
    text: str = Field(max_length=5000, validation_alias=AliasChoices("text", "content"))
