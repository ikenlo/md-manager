"""Симуляція Meta для розробки. Підключається лише при MOCK_META=true і APP_ENV≠production."""

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.routes.dialogues import dialogue_out, message_out
from app.database import get_db
from app.models import Channel, CrmClient, Dialogue, Message, OutboundQueue, User
from app.models.base import utcnow
from app.services import dialogues as svc
from app.services.adapters.mock import DUMMY_JPG, FAIL_MARKER
from app.services.events import NEW_MESSAGE, events
from app.services.media import asset_url, save_asset

router = APIRouter(prefix="/api/_test", tags=["dev: simulation"])

DIALOGUE_UPDATED = "dialogue_updated"


class SimulateInboundRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=255)
    username: str = Field("", max_length=100)
    text: str = Field(min_length=1, max_length=5000)
    channel: Literal["instagram", "facebook"] = "instagram"


class SimulateAttachmentRequest(BaseModel):
    dialogue_uuid: str


class TriggerFailureRequest(BaseModel):
    dialogue_uuid: str
    text: str = Field("Тест збою відправки", max_length=4900)


def _dialogue_or_404(db: Session, uuid: str) -> Dialogue:
    d = svc.get_dialogue(db, uuid)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Діалог не знайдено")
    return d


async def _emit_new_message(d: Dialogue, m: Message, with_dialogue: bool) -> None:
    payload = {"dialogue_uuid": d.uuid, "message": message_out(m).model_dump(mode="json")}
    if with_dialogue:
        payload["dialogue"] = dialogue_out(d, m).model_dump(mode="json")
    await events.emit(NEW_MESSAGE, payload)


async def _emit_dialogue_updated(d: Dialogue) -> None:
    await events.emit(
        DIALOGUE_UPDATED,
        {
            "dialogue_uuid": d.uuid,
            "unread_count": d.unread_count,
            "status": d.status,
            "last_message_at": d.last_message_at.isoformat() if d.last_message_at else None,
            "last_inbound_at": d.last_inbound_at.isoformat() if d.last_inbound_at else None,
        },
    )


@router.post("/simulate_inbound", status_code=201, summary="Нове вхідне від нового клієнта")
async def simulate_inbound(
    body: SimulateInboundRequest, db: Session = Depends(get_db), _: User = Depends(current_user)
) -> dict[str, str]:
    channel = db.scalar(
        select(Channel)
        .where(Channel.channel_type == body.channel, Channel.deleted_at.is_(None))
        .order_by(Channel.id)
    )
    if channel is None:
        channel = Channel(
            channel_type=body.channel,
            account_name=f"mock-{body.channel}",
            status="mock",
            webhook_status="active",
        )
        db.add(channel)
    tail = uuid4().hex[:12]
    client = CrmClient(
        name=body.client_name.strip(),
        username=body.username.strip().lstrip("@") or None,
        instagram_handle=(body.username.strip().lstrip("@") or None)
        if body.channel == "instagram"
        else None,
        meta_ig_user_id=f"mock_ig_{tail}" if body.channel == "instagram" else None,
        meta_fb_user_id=f"mock_fb_{tail}" if body.channel == "facebook" else None,
        is_anonymous=True,
    )
    now = utcnow()
    d = Dialogue(
        client=client,
        channel=channel,
        status="new",
        unread_count=1,
        last_inbound_at=now,
        last_message_at=now,
    )
    m = Message(
        dialogue=d,
        sender_type="client",
        content=body.text.strip(),
        direction="inbound",
        status="delivered",
        external_id=f"mock_msg_{uuid4().hex[:12]}",
        created_at=now,
    )
    db.add_all([d, m])
    db.commit()
    db.refresh(d)
    await _emit_new_message(d, m, with_dialogue=True)
    await _emit_dialogue_updated(d)
    return {"dialogue_uuid": d.uuid, "message_uuid": m.uuid}


@router.post("/simulate_attachment", status_code=201, summary="Фото від клієнта в діалозі")
async def simulate_attachment(
    body: SimulateAttachmentRequest, db: Session = Depends(get_db), _: User = Depends(current_user)
) -> dict[str, str]:
    d = _dialogue_or_404(db, body.dialogue_uuid)
    m = db.scalar(
        select(Message)
        .where(Message.dialogue_id == d.id, Message.direction == "inbound")
        .order_by(Message.id.desc())
    )
    created = m is None
    if created:
        now = utcnow()
        m = Message(
            dialogue_id=d.id,
            sender_type="client",
            content="",
            direction="inbound",
            status="delivered",
            external_id=f"mock_msg_{uuid4().hex[:12]}",
            created_at=now,
        )
        db.add(m)
        db.flush()
        d.last_inbound_at = d.last_message_at = now
        d.unread_count += 1
    asset = save_asset(db, d, m, DUMMY_JPG, "image/jpeg", "jpg", meta_url="mock://attachment")
    url = asset_url(asset)
    # новий список — щоб SQLAlchemy помітив зміну JSON
    m.attachments = [
        *(m.attachments or []),
        {
            "url": url,
            "type": "image/jpeg",
            "name": f"photo-{asset.uuid[:8]}.jpg",
            "size": asset.file_size,
        },
    ]
    db.commit()
    db.refresh(d)
    await _emit_new_message(d, m, with_dialogue=False)
    if created:
        await _emit_dialogue_updated(d)
    return {"message_uuid": m.uuid, "attachment_url": url}


@router.post(
    "/trigger_outbound_failure",
    status_code=201,
    summary="Вихідне, яке mock-адаптер не відправить",
    description=f"Текст отримує префікс `{FAIL_MARKER}`; після MAX_OUTBOUND_RETRIES — `failed`.",
)
async def trigger_outbound_failure(
    body: TriggerFailureRequest, db: Session = Depends(get_db), _: User = Depends(current_user)
) -> dict[str, str]:
    d = _dialogue_or_404(db, body.dialogue_uuid)
    m = svc.create_outbound_message(db, d, f"{FAIL_MARKER} {body.text.strip()}".strip())
    q = db.scalar(select(OutboundQueue).where(OutboundQueue.message_id == m.id))
    await _emit_new_message(d, m, with_dialogue=False)
    return {"message_uuid": m.uuid, "queue_uuid": q.uuid}
