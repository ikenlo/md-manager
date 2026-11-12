"""AI-адміністратор у діалозі: запустити, переглянути, погодити або відхилити відповідь.

Відповідь AI клієнту не йде, доки людина не натисне «Погодити» (human-in-the-loop).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.database import get_db
from app.models import AISuggestion, Dialogue, Message, User
from app.schemas.ai import (
    AIApproveRequest,
    AIApproveResponse,
    AIPendingResponse,
    AIRejectRequest,
    AIRejectResponse,
    AIRespondResponse,
    AISuggestionOut,
)
from app.services.adapters.ollama_base import OllamaDisabledError
from app.services.ai_agent import build_messages_from_dialogue, run_agent
from app.services.ai_suggestions import (
    approve_suggestion,
    build_confirmation_text,
    get_pending_for_dialogue,
    reject_suggestion,
    save_suggestion,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dialogues/{dialogue_uuid}/ai", tags=["ai"])

HISTORY_LIMIT = 10


def _get_dialogue_or_404(db: Session, dialogue_uuid: str) -> Dialogue:
    d = db.scalar(
        select(Dialogue).where(Dialogue.uuid == dialogue_uuid, Dialogue.deleted_at.is_(None))
    )
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dialogue not found")
    return d


def _get_suggestion_or_404(db: Session, dialogue: Dialogue, suggestion_uuid: str) -> AISuggestion:
    s = db.scalar(
        select(AISuggestion).where(
            AISuggestion.uuid == suggestion_uuid, AISuggestion.dialogue_id == dialogue.id
        )
    )
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Suggestion not found")
    return s


@router.post(
    "/respond",
    response_model=AIRespondResponse,
    summary="Запустити AI на діалозі",
    description=(
        "AI читає останні повідомлення діалогу й готує відповідь. Вона зберігається як pending "
        "і НЕ надсилається клієнту, доки її не погодять. Попередня pending-пропозиція діалогу "
        "стає expired."
    ),
    responses={
        400: {"description": "У діалозі немає повідомлень"},
        404: {"description": "Діалог не знайдено"},
        503: {"description": "AI вимкнено (OLLAMA_ENABLED=false)"},
    },
)
async def ai_respond(
    dialogue_uuid: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> AIRespondResponse:
    dialogue = _get_dialogue_or_404(db, dialogue_uuid)
    history = build_messages_from_dialogue(dialogue, limit=HISTORY_LIMIT)
    if not history:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dialogue has no messages")
    last_message = db.scalar(
        select(Message)
        .where(Message.dialogue_id == dialogue.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )

    try:
        result = await run_agent(history)
    except OllamaDisabledError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI вимкнено") from e

    suggestion = save_suggestion(
        db=db,
        dialogue_id=dialogue.id,
        message_id=last_message.id if last_message else None,
        content=result["content"],
        proposed_booking=result.get("proposed_booking"),
        intent=result["intent"],
    )
    return AIRespondResponse(
        suggestion_uuid=suggestion.uuid,
        content=suggestion.content,
        intent=suggestion.intent,
        needs_approval=result["needs_approval"],
        proposed_booking=suggestion.proposed_booking,
        suggested_message=build_confirmation_text(suggestion),
    )


@router.get("/pending", response_model=AIPendingResponse, summary="Поточна пропозиція AI")
def ai_pending(
    dialogue_uuid: str, db: Session = Depends(get_db), _: User = Depends(current_user)
) -> AIPendingResponse:
    dialogue = _get_dialogue_or_404(db, dialogue_uuid)
    s = get_pending_for_dialogue(db, dialogue.id)
    if s is None:
        return AIPendingResponse(suggestion=None)
    return AIPendingResponse(
        suggestion=AISuggestionOut(
            uuid=s.uuid,
            content=s.content,
            intent=s.intent,
            proposed_booking=s.proposed_booking,
            status=s.status,
            created_at=s.created_at,
            suggested_message=build_confirmation_text(s),
        )
    )


@router.post(
    "/{suggestion_uuid}/approve",
    response_model=AIApproveResponse,
    summary="Погодити відповідь AI",
    description=(
        "Надсилає клієнту `message_text`, якщо його задано. Інакше: для запису — готове "
        "підтвердження «Вас записано на {послуга} {ДД.ММ.РРРР} о {час}», для решти — текст AI. "
        "Запис (proposed_booking) створюється тут; його помилка → 400, нічого не надіслано."
    ),
    responses={
        400: {"description": "Пропозиція вже не pending, запис не вдався або порожній текст"},
        404: {"description": "Діалог або пропозицію не знайдено"},
    },
)
async def ai_approve(
    dialogue_uuid: str,
    suggestion_uuid: str,
    body: AIApproveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AIApproveResponse:
    dialogue = _get_dialogue_or_404(db, dialogue_uuid)
    suggestion = _get_suggestion_or_404(db, dialogue, suggestion_uuid)
    if suggestion.status != "pending":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Status is '{suggestion.status}', not 'pending'"
        )

    # той самий текст, що /respond і /pending показали як suggested_message
    custom = (body.message_text or "").strip()
    text = custom or build_confirmation_text(suggestion).strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Порожній текст — вкажіть message_text")
    # що реально пішло клієнту (сервіс відправляє suggestion.content)
    suggestion.content = text

    try:
        approved = await approve_suggestion(db, suggestion_uuid, user.id)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    # повідомлення погодження створюється з часом resolved_at — так знаходимо саме його
    msg = db.scalar(
        select(Message).where(
            Message.dialogue_id == dialogue.id,
            Message.direction == "outbound",
            Message.created_at == approved.resolved_at,
        )
    )
    return AIApproveResponse(
        message_uuid=msg.uuid if msg else "", suggestion_uuid=approved.uuid, status=approved.status
    )


@router.post(
    "/{suggestion_uuid}/reject",
    response_model=AIRejectResponse,
    summary="Відхилити відповідь AI",
    responses={
        400: {"description": "Пропозиція вже не pending"},
        404: {"description": "Діалог або пропозицію не знайдено"},
    },
)
def ai_reject(
    dialogue_uuid: str,
    suggestion_uuid: str,
    body: AIRejectRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AIRejectResponse:
    dialogue = _get_dialogue_or_404(db, dialogue_uuid)
    _get_suggestion_or_404(db, dialogue, suggestion_uuid)
    try:
        rejected = reject_suggestion(db, suggestion_uuid, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    if body.reason:
        # причина — лише в лог (без даних клієнта); окремого поля в таблиці немає
        logger.info(
            "AI suggestion %s rejected with reason (len=%d)", suggestion_uuid, len(body.reason)
        )
    return AIRejectResponse(suggestion_uuid=rejected.uuid, status=rejected.status)
