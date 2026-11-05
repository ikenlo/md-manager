"""Обробка вхідного повідомлення клієнта з будь-якого каналу.

Зберегти → (пауза? ключові слова?) → AI-агент → зберегти відповідь → повернути текст.
Відправку робить канал, що викликав (Telegram/Instagram).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import clients as cl
from app.agent.runner import Agent
from app.agent.tools import do_handoff
from app.db.models import Channel, ConversationState, Message, MessageRole
from app.notify import Notifier

log = logging.getLogger(__name__)

AI_DISCLOSURE = "🤖 Я AI-помічник салону M&D: можу записати або покликати адміністратора.\n\n"
HANDOFF_REPLY = "Зараз покличу адміністратора — він відповість тут найближчим часом 🙏"
HANDOFF_RE = re.compile(
    r"адміністратор|адмін\b|живу людин|жива людина|з людиною|оператор|менеджер|скарг",
    re.IGNORECASE,
)


class Dialog:
    def __init__(
        self,
        engine: Engine,
        agent: Agent | None,
        notifier: Notifier,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.engine = engine
        self.agent = agent
        self.notifier = notifier
        self.clock = clock
        self._locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def handle_inbound(
        self,
        channel: Channel,
        client_id: int,
        text: str,
        *,
        external_id: str | None = None,
    ) -> str | None:
        """Повертає текст відповіді клієнту або None (бот мовчить)."""
        now = self.clock()
        with Session(self.engine) as s, s.begin():
            conv = cl.get_conversation(s, client_id, channel)
            if conv.state == ConversationState.closed:
                conv.state = ConversationState.ai
            cl.add_message(s, conv, MessageRole.client, text, external_id=external_id, now=now)
            conv_id, state = conv.id, conv.state
            globally_paused = cl.ai_globally_paused(s)
            client_name = conv.client.name or "Клієнт"

        async with self._locks[conv_id]:
            if state == ConversationState.paused:
                # Адмін веде діалог: пересилаємо текст, щоб він бачив (у TG інакше не видно).
                await self.notifier.admin(f"💬 #{conv_id} {client_name}: {text}")
                return None
            if globally_paused or self.agent is None:
                await self.notifier.admin(
                    f"💬 #{conv_id} {client_name} (AI вимкнено): {text}\n/reply {conv_id} текст"
                )
                return None
            if HANDOFF_RE.search(text):
                await do_handoff(
                    self.engine, self.notifier, conv_id, "Клієнт просить людину", text, now
                )
                return self._store_reply(conv_id, HANDOFF_REPLY)

            result = await self.agent.reply(conv_id, now)
            if not result.text:
                return None
            return self._store_reply(conv_id, result.text)

    def _store_reply(self, conv_id: int, text: str) -> str:
        with Session(self.engine) as s, s.begin():
            first = not s.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.conversation_id == conv_id, Message.role == MessageRole.assistant)
            )
            if first:
                text = AI_DISCLOSURE + text
            conv = cl.get_conversation_by_id(s, conv_id)
            cl.add_message(s, conv, MessageRole.assistant, text, now=self.clock())
        return text

    async def handle_telegram(self, message) -> None:  # noqa: ANN001
        with Session(self.engine) as s, s.begin():
            client = cl.get_or_create_tg_client(
                s, message.from_user.id, message.from_user.first_name or ""
            )
            client_id = client.id
        reply = await self.handle_inbound(
            Channel.telegram, client_id, message.text, external_id=str(message.message_id)
        )
        if reply:
            await message.answer(reply, parse_mode=None)
