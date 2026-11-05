"""Цикл Claude Messages API з tool use.

Захисні правила в коді (docs/SPEC.md, «AI-агент»):
- ліміт викликів інструментів на одне повідомлення клієнта (AI_MAX_TOOL_CALLS, 8);
- таймаут на всю відповідь (AI_TIMEOUT_S, 30 с) → «Секунду, уточню…» + handoff;
- refusal / max_tokens / помилка API → той самий безпечний шлях.
Prompt caching: інструменти + статична частина системного промпту кешуються;
поточна дата й час ідуть окремим блоком після точки кешу.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import anthropic
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import clients as cl
from app.admin.queries import price_list
from app.agent import tools as t
from app.agent import usage
from app.config import Settings
from app.db.models import Channel, Client, Conversation, MessageRole, SalonSetting
from app.notify import Notifier
from app.text import WEEKDAYS_FULL

log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "system.md"
FALLBACK_TEXT = "Секунду, уточню у адміністратора 🙏"
CHANNEL_NAMES = {Channel.telegram: "Telegram", Channel.instagram: "Instagram Direct"}
SETTING_KEYS = (
    "salon_name", "address", "phone", "hours", "about",
    "rules_lateness", "rules_cancel", "rules_prepay",
)  # fmt: skip


class MessagesAPI(Protocol):
    async def create(self, **kwargs: Any) -> Any: ...


class ClaudeClient(Protocol):
    messages: MessagesAPI


@dataclass
class AgentResult:
    text: str
    handed_off: bool = False
    bookings_created: list[int] = field(default_factory=list)
    tool_calls: int = 0
    failed: bool = False


def _tools_with_cache() -> list[dict[str, Any]]:
    tools = [dict(x) for x in t.TOOLS]
    tools[-1]["cache_control"] = {"type": "ephemeral"}
    return tools


CACHED_TOOLS = _tools_with_cache()


def build_static_prompt(session: Session, channel: Channel) -> str:
    """Стабільна частина промпту (факти салону + прайс). Не містить часу — кешується."""
    values = {k: "" for k in SETTING_KEYS}
    for row in session.scalars(select(SalonSetting).where(SalonSetting.key.in_(SETTING_KEYS))):
        values[row.key] = row.value
    values["salon_name"] = values["salon_name"] or "M&D"
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(
        channel=CHANNEL_NAMES.get(channel, channel.value),
        price_list=price_list(session),
        **{k: (v or "—") for k, v in values.items() if k != "price_list"},
    )


def build_dynamic_prompt(settings: Settings, now: datetime, client_name: str) -> str:
    """Змінна частина: поточна дата/час (без неї модель плутає «завтра») та ім'я клієнта."""
    local = now.astimezone(settings.zone)
    tm = local.date() + timedelta(days=1)
    return (
        f"Зараз у Києві: {WEEKDAYS_FULL[local.weekday()]}, {local:%Y-%m-%d %H:%M}. "
        f"Завтра — {WEEKDAYS_FULL[tm.weekday()]}, {tm.isoformat()}.\n"
        f"Ім'я клієнта: {client_name or 'невідоме — запитай перед записом'}."
    )


def history_to_messages(rows: list[Any]) -> list[dict[str, Any]]:
    """Повідомлення з БД → messages для API. Починається з user; однакові ролі зливаються."""
    out: list[dict[str, Any]] = []
    for m in rows:
        if m.role == MessageRole.client:
            role, text = "user", m.text
        elif m.role == MessageRole.admin:
            role, text = "assistant", f"[Відповідь адміністратора] {m.text}"
        else:
            role, text = "assistant", m.text
        if not out and role != "user":
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n\n" + text
        else:
            out.append({"role": role, "content": text})
    return out


class Agent:
    def __init__(
        self,
        client: ClaudeClient,
        engine: Engine,
        settings: Settings,
        notifier: Notifier,
    ) -> None:
        self.client = client
        self.engine = engine
        self.settings = settings
        self.notifier = notifier

    async def reply(self, conversation_id: int, now: datetime) -> AgentResult:
        with Session(self.engine) as s:
            conv = s.get(Conversation, conversation_id)
            client = s.get(Client, conv.client_id)
            ctx = t.ToolContext(
                engine=self.engine, settings=self.settings, notifier=self.notifier,
                client_id=client.id, conversation_id=conv.id, channel=conv.channel, now=now,
            )  # fmt: skip
            system = [
                {
                    "type": "text",
                    "text": build_static_prompt(s, conv.channel),
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": build_dynamic_prompt(self.settings, now, client.name)},
            ]
            messages = history_to_messages(
                cl.recent_messages(s, conv, self.settings.ai_history_messages)
            )
        if not messages:
            return AgentResult(text="", failed=True)

        try:
            async with asyncio.timeout(self.settings.ai_timeout_s):
                result = await self._loop(ctx, system, messages)
        except TimeoutError:
            log.warning("agent timeout conv=%s", conversation_id)
            result = AgentResult(text=FALLBACK_TEXT, failed=True)
        except anthropic.APIError as e:
            log.error("agent api error conv=%s: %s", conversation_id, type(e).__name__)
            result = AgentResult(text=FALLBACK_TEXT, failed=True)

        if result.failed and not ctx.handed_off:
            await t.do_handoff(
                self.engine, self.notifier, conversation_id,
                "AI не зміг відповісти (таймаут, ліміт або помилка)", now=now,
            )  # fmt: skip
            ctx.handed_off = True
        result.handed_off = ctx.handed_off
        result.bookings_created = ctx.bookings_created
        return result

    async def _loop(
        self, ctx: t.ToolContext, system: list[dict[str, Any]], messages: list[dict[str, Any]]
    ) -> AgentResult:
        calls = 0
        while True:
            response = await self.client.messages.create(
                model=self.settings.ai_model,
                max_tokens=4096,  # з запасом: thinking теж рахується в max_tokens
                system=system,
                tools=CACHED_TOOLS,
                messages=messages,
                output_config={"effort": self.settings.ai_effort},
            )
            with Session(self.engine) as s, s.begin():
                usage.record(s, ctx.conversation_id, self.settings.ai_model, response.usage)

            if response.stop_reason in ("refusal", "max_tokens"):
                log.warning(
                    "agent stop_reason=%s conv=%s", response.stop_reason, ctx.conversation_id
                )
                return AgentResult(text=FALLBACK_TEXT, tool_calls=calls, failed=True)

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_uses:
                text = "\n".join(b.text for b in response.content if b.type == "text").strip()
                if not text:
                    return AgentResult(text=FALLBACK_TEXT, tool_calls=calls, failed=True)
                return AgentResult(text=text, tool_calls=calls)

            if calls + len(tool_uses) > self.settings.ai_max_tool_calls:
                log.warning("agent tool limit conv=%s", ctx.conversation_id)
                return AgentResult(text=FALLBACK_TEXT, tool_calls=calls, failed=True)

            # Повертаємо content без змін (разом із thinking-блоками).
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in tool_uses:
                calls += 1
                payload, is_error = await t.execute(ctx, block.name, block.input)
                log.info("tool %s error=%s conv=%s", block.name, is_error, ctx.conversation_id)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(payload, ensure_ascii=False),
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": results})


def make_client(settings: Settings) -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None, max_retries=1)
