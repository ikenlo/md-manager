"""FastAPI-застосунок: вебхуки каналів, запуск бота і планувальника."""

from __future__ import annotations

import asyncio
import hmac
import logging
from contextlib import asynccontextmanager
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import FastAPI, Request, Response

from app.agent.runner import Agent, make_client
from app.channels import telegram as tg
from app.config import Settings, get_settings
from app.db.models import Channel
from app.db.session import get_engine
from app.dialog import Dialog
from app.notify import Notifier

log = logging.getLogger("mds")


class AppState:
    settings: Settings
    notifier: Notifier
    dialog: Dialog
    bot: Bot | None = None
    dp: Dispatcher | None = None
    tasks: list[asyncio.Task[Any]]


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    engine = get_engine()
    state.settings = settings
    state.notifier = Notifier()
    state.tasks = []
    agent = None
    if settings.anthropic_api_key:
        agent = Agent(make_client(settings), engine, settings, state.notifier)
    else:
        log.warning("ANTHROPIC_API_KEY not set — AI disabled, messages go to admins")
    state.dialog = Dialog(engine, agent, state.notifier)

    if settings.tg_bot_token:
        bot = Bot(settings.tg_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        state.bot = bot
        state.notifier.admin_sender = tg.admin_sender(bot, settings.tg_admin_chat_id)
        state.notifier.senders[Channel.telegram] = tg.telegram_sender(bot)
        state.dp = tg.build_dispatcher(engine, settings, state.notifier, dialog=state.dialog)
        if settings.public_url:
            await bot.set_webhook(
                f"{settings.public_url.rstrip('/')}/webhook/telegram",
                secret_token=settings.tg_webhook_secret or None,
                drop_pending_updates=False,
            )
            log.info("telegram: webhook mode")
        else:
            await bot.delete_webhook()
            state.tasks.append(
                asyncio.create_task(state.dp.start_polling(bot, handle_signals=False))
            )
            log.info("telegram: polling mode")
    else:
        log.warning("TG_BOT_TOKEN not set — Telegram disabled")

    yield

    for t in state.tasks:
        t.cancel()
    if state.dp is not None and state.tasks:
        await state.dp.stop_polling()
    if state.bot is not None:
        await state.bot.session.close()


app = FastAPI(title="MDs manager", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request) -> Response:
    settings = state.settings
    expected = settings.tg_webhook_secret
    got = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not expected or not hmac.compare_digest(got, expected):
        return Response(status_code=403)
    if state.bot is None or state.dp is None:
        return Response(status_code=503)
    update = Update.model_validate(await request.json(), context={"bot": state.bot})
    await state.dp.feed_update(state.bot, update)
    return Response(status_code=200)
