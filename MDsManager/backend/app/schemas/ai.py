from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AIRespondResponse(BaseModel):
    suggestion_uuid: str
    content: str
    intent: str
    needs_approval: bool
    proposed_booking: dict[str, Any] | None = None
    # що отримає клієнт після схвалення без правок (для запису — готове підтвердження)
    suggested_message: str


class AISuggestionOut(BaseModel):
    uuid: str
    content: str
    intent: str
    proposed_booking: dict[str, Any] | None = None
    status: str
    created_at: datetime
    suggested_message: str


class AIPendingResponse(BaseModel):
    suggestion: AISuggestionOut | None = None


class AIApproveRequest(BaseModel):
    # None або порожній — для запису текст підтвердження складається сам, інакше — текст AI
    message_text: str | None = Field(default=None, max_length=5000)


class AIApproveResponse(BaseModel):
    message_uuid: str
    suggestion_uuid: str
    status: str


class AIRejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class AIRejectResponse(BaseModel):
    suggestion_uuid: str
    status: str
