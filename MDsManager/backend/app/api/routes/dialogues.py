from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.database import get_db
from app.models import Dialogue, Message, User
from app.schemas.dialogue import (
    ChannelOut,
    ChannelType,
    ClientOut,
    DialogueList,
    DialogueOut,
    DialogueStatus,
    MessageIn,
    MessageOut,
)
from app.services import dialogues as svc

router = APIRouter(prefix="/api/dialogues", tags=["dialogues"])


def message_out(m: Message) -> MessageOut:
    return MessageOut(
        uuid=m.uuid, sender_type=m.sender_type, content=m.content, created_at=m.created_at
    )


def dialogue_out(d: Dialogue, last: Message | None) -> DialogueOut:
    c, ch = d.client, d.channel
    return DialogueOut(
        uuid=d.uuid,
        status=d.status,
        last_message_at=d.last_message_at,
        client=ClientOut(
            uuid=c.uuid, name=c.name, instagram_handle=c.instagram_handle, phone=c.phone
        ),
        channel=ChannelOut(
            uuid=ch.uuid, channel_type=ch.channel_type, account_name=ch.account_name
        ),
        tags=[t.tag_name for t in d.tags],
        last_message=message_out(last) if last else None,
    )


def _get_or_404(db: Session, uuid: str) -> Dialogue:
    d = svc.get_dialogue(db, uuid)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Діалог не знайдено")
    return d


@router.get("", response_model=DialogueList)
def list_dialogues(
    status_: DialogueStatus | None = Query(None, alias="status"),
    channel: ChannelType | None = None,
    tag: str | None = Query(None, max_length=64),
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
) -> DialogueList:
    rows, total = svc.list_dialogues(
        db, status=status_, channel_type=channel, tag=tag, search=q, limit=limit, offset=offset
    )
    last = svc.last_messages(db, [d.id for d in rows])
    return DialogueList(items=[dialogue_out(d, last.get(d.id)) for d in rows], total=total)


@router.get("/{uuid}/messages", response_model=list[MessageOut])
def get_messages(
    uuid: str,
    limit: int = Query(100, ge=1, le=500),
    before_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
) -> list[MessageOut]:
    d = _get_or_404(db, uuid)
    return [message_out(m) for m in svc.list_messages(db, d, limit, before_id)]


@router.post("/{uuid}/messages", response_model=MessageOut, status_code=201)
def post_message(
    uuid: str,
    body: MessageIn,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
) -> MessageOut:
    d = _get_or_404(db, uuid)
    # Фаза 1: лише зберігаємо; відправку в канал додамо разом з інтеграціями
    return message_out(svc.add_message(db, d, body.sender_type, body.content.strip()))
