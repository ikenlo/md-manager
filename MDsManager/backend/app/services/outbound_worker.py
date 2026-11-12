"""Воркер черги вихідних: outbound_queue → MetaAdapter → статус повідомлення.

Кожен елемент обробляється у три кроки, щоб не тримати SQLite-блокування під час мережевого
виклику: (1) коротка транзакція — читаємо дані; (2) відправка без сесії; (3) коротка транзакція —
записуємо результат. Фіксація — по одному елементу.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.database import SessionLocal
from app.models import OutboundQueue
from app.models.base import utcnow
from app.services.adapters.base import MetaAdapter
from app.services.adapters.factory import get_meta_adapter
from app.services.events import MESSAGE_STATUS, EventBus, events

log = logging.getLogger("mds.outbound")

BATCH_SIZE = 20
ALREADY_SENT = ("sent", "delivered", "read")
NO_RECIPIENT = "no recipient id"


def recipient_for(channel_type: str, ig_id: str | None, fb_id: str | None) -> str | None:
    if channel_type == "instagram":
        return ig_id
    if channel_type == "facebook":
        return fb_id
    return None  # Telegram та інші — не через Meta


@dataclass
class _Job:
    recipient: str
    text: str
    channel: str


class OutboundWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session] = SessionLocal,
        adapter_factory: Callable[[], MetaAdapter] = get_meta_adapter,
        bus: EventBus = events,
    ) -> None:
        self.log = log
        self.session_factory = session_factory
        self.adapter_factory = adapter_factory
        self.bus = bus

    async def process_once(self) -> dict[str, Any]:
        stats: dict[str, Any] = {"processed": 0, "sent": 0, "failed": 0, "errors": []}
        with self.session_factory() as db:
            ids = db.scalars(
                select(OutboundQueue.id)
                .where(OutboundQueue.status == "pending", OutboundQueue.next_retry_at <= utcnow())
                .order_by(OutboundQueue.created_at, OutboundQueue.id)
                .limit(BATCH_SIZE)
            ).all()
        if not ids:
            return stats

        adapter = self.adapter_factory()
        for qid in ids:
            try:
                await self._process_item(qid, adapter, stats)
            except Exception as e:  # БД/неочікуване — не зупиняємо решту
                self.log.exception("Черга вихідних: збій елемента id=%s", qid)
                stats["errors"].append({"queue_id": qid, "error": type(e).__name__})

        if stats["processed"]:
            retrying = stats["processed"] - stats["sent"] - stats["failed"]
            self.log.info(
                "Outbound worker processed %d message(s): %d sent, %d failed, %d retrying",
                stats["processed"],
                stats["sent"],
                stats["failed"],
                retrying,
            )
        return stats

    async def _process_item(self, qid: int, adapter: MetaAdapter, stats: dict[str, Any]) -> None:
        # 1. Підготовка
        with self.session_factory() as db:
            item = db.get(OutboundQueue, qid)
            if item is None or item.status != "pending":
                return  # уже оброблено
            stats["processed"] += 1
            msg = item.message
            if msg is None:
                item.status, item.last_error = "failed", "message deleted"
                db.commit()
                stats["failed"] += 1
                stats["errors"].append({"queue_id": qid, "error": "message deleted"})
                return
            if msg.status in ALREADY_SENT:  # відправили, але впали до запису черги
                item.status = "sent"
                db.commit()
                stats["sent"] += 1
                return
            d = msg.dialogue
            recipient = recipient_for(
                d.channel.channel_type, d.client.meta_ig_user_id, d.client.meta_fb_user_id
            )
            if not recipient:
                item.attempts += 1
                item.status, item.last_error = "failed", NO_RECIPIENT
                msg.status = "failed"
                db.commit()
                stats["failed"] += 1
                stats["errors"].append({"queue_id": qid, "error": NO_RECIPIENT})
                await self._emit_status(msg.uuid, d.uuid, "failed", None)
                return
            job = _Job(recipient=recipient, text=msg.content, channel=d.channel.channel_type)

        # 2. Відправка (без відкритої сесії)
        result: dict[str, str] | None = None
        error: Exception | None = None
        try:
            result = dict(await adapter.send_message(job.recipient, job.text, job.channel))
            if result.get("status") == "failed" or not result.get("external_id"):
                raise RuntimeError(f"Meta відповіла: {result.get('status')}")
        except Exception as e:
            error = e

        # 3. Запис результату
        now = utcnow()
        with self.session_factory() as db:
            item = db.get(OutboundQueue, qid)
            if item is None:
                return
            msg = item.message
            d = msg.dialogue
            if error is None and result is not None:
                msg.status = "sent"
                msg.external_id = result["external_id"]
                item.status, item.last_error = "sent", None
                d.last_outbound_at = now
                event = ("sent", msg.external_id)
                stats["sent"] += 1
            else:
                item.attempts += 1
                item.last_error = f"{type(error).__name__}: {error}"[:1000]
                if item.attempts >= get_settings().max_outbound_retries:
                    item.status = "failed"
                    msg.status = "failed"
                    event = ("failed", None)
                    stats["failed"] += 1
                else:
                    step = timedelta(seconds=get_settings().outbound_retry_base_seconds)
                    item.next_retry_at = now + step * item.attempts
                    event = None
                stats["errors"].append({"queue_id": qid, "error": type(error).__name__})
            msg_uuid, d_uuid = msg.uuid, d.uuid
            db.commit()

        if event:
            await self._emit_status(msg_uuid, d_uuid, *event)

    async def _emit_status(
        self, message_uuid: str, dialogue_uuid: str, status: str, external_id: str | None
    ) -> None:
        await self.bus.emit(
            MESSAGE_STATUS,
            {
                "message_uuid": message_uuid,
                "dialogue_uuid": dialogue_uuid,
                "status": status,
                "external_id": external_id,
            },
        )

    async def run_forever(self) -> None:
        while True:
            try:
                await self.process_once()
            except Exception:
                self.log.exception("Outbound worker: збій циклу")
            await asyncio.sleep(get_settings().outbound_interval_seconds)
