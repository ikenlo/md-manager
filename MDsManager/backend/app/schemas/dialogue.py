from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

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
    uuid: str
    sender_type: str
    content: str
    created_at: datetime


class DialogueOut(BaseModel):
    uuid: str
    status: str
    last_message_at: datetime | None
    client: ClientOut
    channel: ChannelOut
    tags: list[str]
    last_message: MessageOut | None
    unread: int = 0


class DialogueList(BaseModel):
    items: list[DialogueOut]
    total: int


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    sender_type: Literal["human"] = "human"
