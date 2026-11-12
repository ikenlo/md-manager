"""Фейковий Telegram: апдейти йдуть через справжній Dispatcher, виклики Bot API записуються."""

from __future__ import annotations

import itertools
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import EditMessageText, SendMessage, TelegramMethod
from aiogram.types import Chat, Message, Update

from app.channels.telegram import build_dispatcher
from app.db.models import Channel
from app.notify import Notifier

ADMIN_ID = 1001
ADMIN_CHAT = -5000
CLIENT_ID = 2002

_ids = itertools.count(1)


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None):  # noqa: ANN201
        self.calls.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=next(_ids),
                date=datetime.now(UTC),
                chat=Chat(
                    id=method.chat_id, type="private" if int(method.chat_id) > 0 else "group"
                ),
                text=method.text,
            )
        if isinstance(method, EditMessageText):
            return True
        return True

    async def stream_content(self, *a: Any, **kw: Any) -> AsyncGenerator[bytes, None]:
        yield b""

    async def close(self) -> None:
        pass


class TG:
    def __init__(self, engine, settings, clock, dialog=None) -> None:  # noqa: ANN001
        self.session = FakeSession()
        self.bot = Bot("42:TEST", session=self.session)
        self.admin_msgs: list[str] = []
        self.client_msgs: list[tuple[str, str]] = []

        async def admin_sender(text: str, keyboard: Any = None) -> None:
            self.admin_msgs.append(text)

        async def tg_sender(rid: str, text: str) -> bool:
            self.client_msgs.append((rid, text))
            return True

        self.notifier = Notifier(admin_sender=admin_sender, senders={Channel.telegram: tg_sender})
        self.dp = build_dispatcher(engine, settings, self.notifier, dialog=dialog, clock=clock)
        self._last_bot_msg_id: dict[int, int] = {}

    # --- вхідні апдейти -------------------------------------------------------

    async def _feed(self, payload: dict) -> None:
        update = Update.model_validate(
            {"update_id": next(_ids), **payload}, context={"bot": self.bot}
        )
        await self.dp.feed_update(self.bot, update)

    @staticmethod
    def _chat(chat_id: int) -> dict:
        return {"id": chat_id, "type": "private" if chat_id > 0 else "supergroup", "title": "g"}

    async def send(self, text: str, user_id: int = CLIENT_ID, chat_id: int | None = None) -> None:
        chat_id = chat_id if chat_id is not None else user_id
        entities = (
            [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
            if text.startswith("/")
            else None
        )
        msg = {
            "message_id": next(_ids),
            "date": int(datetime.now(UTC).timestamp()),
            "chat": self._chat(chat_id),
            "from": {"id": user_id, "is_bot": False, "first_name": "Олена"},
            "text": text,
        }
        if entities:
            msg["entities"] = entities
        await self._feed({"message": msg})

    async def contact(self, phone: str, user_id: int = CLIENT_ID) -> None:
        await self._feed(
            {
                "message": {
                    "message_id": next(_ids),
                    "date": int(datetime.now(UTC).timestamp()),
                    "chat": self._chat(user_id),
                    "from": {"id": user_id, "is_bot": False, "first_name": "Олена"},
                    "contact": {"phone_number": phone, "first_name": "Олена", "user_id": user_id},
                }
            }
        )

    async def press(self, data: str, user_id: int = CLIENT_ID, chat_id: int | None = None) -> None:
        chat_id = chat_id if chat_id is not None else user_id
        await self._feed(
            {
                "callback_query": {
                    "id": str(next(_ids)),
                    "from": {"id": user_id, "is_bot": False, "first_name": "Олена"},
                    "chat_instance": "ci",
                    "data": data,
                    "message": {
                        "message_id": next(_ids),
                        "date": int(datetime.now(UTC).timestamp()),
                        "chat": self._chat(chat_id),
                        "from": {"id": 42, "is_bot": True, "first_name": "bot"},
                        "text": "...",
                    },
                }
            }
        )

    # --- вихідні виклики -----------------------------------------------------

    def texts(self, chat_id: int | None = None) -> list[str]:
        out = []
        for c in self.session.calls:
            if isinstance(c, SendMessage | EditMessageText) and (
                chat_id is None or int(c.chat_id or 0) == chat_id
            ):
                out.append(c.text)
        return out

    def last_text(self, chat_id: int | None = None) -> str:
        t = self.texts(chat_id)
        return t[-1] if t else ""

    def buttons(self) -> list[tuple[str, str]]:
        """(текст, callback_data) з клавіатури останнього повідомлення з inline-кнопками."""
        for c in reversed(self.session.calls):
            markup = getattr(c, "reply_markup", None)
            if markup is not None and hasattr(markup, "inline_keyboard"):
                return [
                    (b.text, b.callback_data)
                    for row in markup.inline_keyboard
                    for b in row
                    if b.callback_data
                ]
        return []

    def button(self, startswith: str) -> str:
        for text, data in self.buttons():
            if text.startswith(startswith):
                return data
        raise AssertionError(f"Немає кнопки «{startswith}»: {self.buttons()}")
