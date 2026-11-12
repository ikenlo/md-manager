from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Channel, CrmClient, DialogTag, Dialogue, Message
from app.models.base import utcnow


def list_dialogues(
    db: Session,
    *,
    status: str | None = None,
    channel_type: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Dialogue], int]:
    q = (
        select(Dialogue)
        .join(Dialogue.client)
        .join(Dialogue.channel)
        .where(Dialogue.deleted_at.is_(None))
    )
    if status:
        q = q.where(Dialogue.status == status)
    if channel_type:
        q = q.where(Channel.channel_type == channel_type)
    if tag:
        q = q.where(Dialogue.tags.any(DialogTag.tag_name == tag))
    if search:
        like = f"%{search.strip()}%"
        q = q.where(or_(CrmClient.name.ilike(like), CrmClient.instagram_handle.ilike(like)))

    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(
        q.options(
            selectinload(Dialogue.client),
            selectinload(Dialogue.channel),
            selectinload(Dialogue.tags),
        )
        .order_by(Dialogue.last_message_at.desc().nulls_last(), Dialogue.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def last_messages(db: Session, dialogue_ids: list[int]) -> dict[int, Message]:
    if not dialogue_ids:
        return {}
    latest = (
        select(func.max(Message.id))
        .where(Message.dialogue_id.in_(dialogue_ids))
        .group_by(Message.dialogue_id)
    )
    msgs = db.scalars(select(Message).where(Message.id.in_(latest))).all()
    return {m.dialogue_id: m for m in msgs}


def get_dialogue(db: Session, uuid: str) -> Dialogue | None:
    return db.scalar(select(Dialogue).where(Dialogue.uuid == uuid, Dialogue.deleted_at.is_(None)))


def list_messages(db: Session, dialogue: Dialogue, limit: int, before_id: int | None):
    q = select(Message).where(Message.dialogue_id == dialogue.id)
    if before_id:
        q = q.where(Message.id < before_id)
    rows = db.scalars(q.order_by(Message.id.desc()).limit(limit)).all()
    return list(reversed(rows))


def add_message(db: Session, dialogue: Dialogue, sender_type: str, content: str) -> Message:
    msg = Message(dialogue_id=dialogue.id, sender_type=sender_type, content=content)
    db.add(msg)
    dialogue.last_message_at = utcnow()
    if dialogue.status == "new" and sender_type != "client":
        dialogue.status = "in_progress"
    db.commit()
    db.refresh(msg)
    return msg
