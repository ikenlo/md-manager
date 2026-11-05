"""Адмін-команди в Telegram. Доступ лише для ADMIN_IDS (в адмін-групі або в приватному чаті)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from aiogram import F
from aiogram.filters import Command, CommandObject, Filter
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import clients as cl
from app.admin import queries as q
from app.booking import service as bs
from app.channels.registry import HandlerRegistry
from app.config import Settings
from app.db.models import BookingStatus, Client, Conversation, MessageRole, Service
from app.notify import Notifier
from app.text import (
    ParseError,
    fmt_date_long,
    fmt_slot,
    local_to_utc,
    normalize_phone,
    parse_date,
    parse_time,
)

Clock = Callable[[], datetime]

HELP = """<b>Адмін-команди</b>
/today, /tomorrow, /day 20.11 — розклад
/book — ручний запис
/cancel &lt;id&gt; · /move &lt;id&gt; &lt;дата&gt; &lt;час&gt;
/noshow &lt;id&gt; · /done &lt;id&gt;
/dayoff &lt;майстер&gt; &lt;дата&gt;
/takeover &lt;діалог&gt; · /resume &lt;діалог&gt; · /reply &lt;діалог&gt; &lt;текст&gt;
/pause_all · /resume_all — AI на всіх каналах
/price — прайс · /stats — тиждень
/client &lt;телефон|id&gt; · /forget &lt;телефон&gt;
/link &lt;мітка&gt; — посилання для реклами · /sources [днів] — звідки записи й гроші"""


class IsAdmin(Filter):
    async def __call__(self, event: TelegramObject, settings: Settings) -> bool:
        user = getattr(event, "from_user", None)
        if user is None or user.id not in settings.admin_ids:
            return False
        chat = event.chat if isinstance(event, Message) else getattr(event.message, "chat", None)
        return chat is None or chat.type == "private" or chat.id == settings.tg_admin_chat_id


class ConvCb(CallbackData, prefix="cv"):
    a: str  # takeover | resume
    id: int


class PriceCb(CallbackData, prefix="pr"):
    id: int


class PriceEdit(StatesGroup):
    value = State()


router = HandlerRegistry("admin")
router.filter("message", IsAdmin())
router.filter("callback_query", IsAdmin())


def _today(clock: Clock, settings: Settings):  # noqa: ANN202
    return clock().astimezone(settings.zone).date()


def _int_arg(command: CommandObject) -> int:
    arg = (command.args or "").split()
    if not arg or not arg[0].lstrip("#").isdigit():
        raise ParseError(f"Формат: /{command.command} <id>")
    return int(arg[0].lstrip("#"))


async def _reply_error(message: Message, e: Exception) -> None:
    await message.answer(f"⚠️ {e}")


class MdsMode(Filter):
    async def __call__(self, event: TelegramObject, settings: Settings) -> bool:
        return bool(settings.mds_url)


MDS_OWNED = (
    "today",
    "tomorrow",
    "day",
    "book",
    "cancel",
    "move",
    "noshow",
    "done",
    "dayoff",
    "price",
)


@router.message(Command(*MDS_OWNED), MdsMode())
async def cmd_in_mds(message: Message) -> None:
    await message.answer(
        "Записи, розклад і прайс ведуться в MDS Connect — відкрийте панель MDS. "
        "Тут: /sources, /link, /stats, /takeover, /reply, /pause_all."
    )


@router.message(Command("link"))
async def cmd_link(message: Message, command: CommandObject, settings: Settings) -> None:
    label = cl.clean_label(command.args)
    if not label:
        await _reply_error(
            message,
            ParseError(
                "Формат: /link <мітка>, лише латиниця, цифри, _ і -. Напр.: /link ig_reels_1201"
            ),
        )
        return
    username = settings.tg_bot_username
    if not username:
        try:
            username = (await message.bot.me()).username
        except Exception:  # noqa: BLE001
            username = ""
    tg = f"https://t.me/{username}?start={label}" if username else f"t.me/<бот>?start={label}"
    await message.answer(
        f"🔗 Посилання з міткою «{label}»\nTelegram: {tg}\n"
        f"Instagram: додайте ?ref={label} до посилання ig.me/m/<ваш_акаунт>\n\n"
        "Записи з цих посилань видно в /sources."
    )


@router.message(Command("sources"))
async def cmd_sources(
    message: Message,
    command: CommandObject,
    engine: Engine,
    settings: Settings,
    clock: Clock,
    mds: Any = None,
) -> None:
    from app import marketing

    arg = (command.args or "").strip()
    days = int(arg) if arg.isdigit() and 0 < int(arg) <= 366 else 30
    now = clock()
    if mds is not None:
        from app.integrations.mds import MdsError

        d_to = now.astimezone(settings.zone).date()
        d_from = d_to - timedelta(days=days - 1)
        try:
            visits = await mds.visits(d_from, d_to)
            spend = (await mds.ad_spend(d_from, d_to))["total"]
        except MdsError as e:
            await _reply_error(message, ParseError(f"MDS Connect: {e.message}"))
            return
        await message.answer(
            marketing.format_sources(marketing.aggregate_mds_visits(visits), days, spend)
        )
        return
    with Session(engine) as session:
        rows = marketing.aggregate_local(session, now - timedelta(days=days))
    await message.answer(marketing.format_sources(rows, days))


@router.message(Command("help", "admin"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP, parse_mode="HTML")


# --- розклад -----------------------------------------------------------------


@router.message(Command("today", "tomorrow", "day"))
async def cmd_day(
    message: Message, command: CommandObject, engine: Engine, settings: Settings, clock: Clock
) -> None:
    today = _today(clock, settings)
    try:
        if command.command == "today":
            d = today
        elif command.command == "tomorrow":
            d = today + timedelta(days=1)
        else:
            if not command.args:
                raise ParseError("Формат: /day 20.11")
            d = parse_date(command.args, today)
    except ParseError as e:
        await _reply_error(message, e)
        return
    with Session(engine) as session:
        await message.answer(q.day_schedule(session, d))


@router.message(Command("book"))
async def cmd_book(message: Message, state: FSMContext, engine: Engine) -> None:
    from app.channels.telegram import start_booking

    await start_booking(message, state, engine, mode="admin")


# --- операції із записами --------------------------------------------------


async def _notify_client_about(
    engine: Engine, notifier: Notifier, booking_id: int, text_fn: Callable[[str], str]
) -> str:
    with Session(engine) as session:
        b = q.load_booking(session, booking_id)
        summary = q.booking_summary(b)
        client_id = b.client_id
    delivered = await notifier.client(engine, client_id, text_fn(summary))
    return "клієнта повідомлено" if delivered else "клієнту написати не вдалося — канал закритий"


@router.message(Command("cancel"))
async def cmd_cancel(
    message: Message, command: CommandObject, engine: Engine, notifier: Notifier
) -> None:
    try:
        bid = _int_arg(command)
        await asyncio.to_thread(bs.set_status, bid, BookingStatus.cancelled, engine=engine)
    except (ParseError, bs.BookingError) as e:
        await _reply_error(message, e)
        return
    status = await _notify_client_about(
        engine,
        notifier,
        bid,
        lambda s: f"Ваш запис скасовано: {s}. Щоб записатися знову — напишіть нам.",
    )
    await message.answer(f"🚫 Запис #{bid} скасовано, {status}")


@router.message(Command("move"))
async def cmd_move(
    message: Message, command: CommandObject, engine: Engine, settings: Settings,
    notifier: Notifier, clock: Clock,
) -> None:  # fmt: skip
    try:
        parts = (command.args or "").split()
        if len(parts) != 3 or not parts[0].lstrip("#").isdigit():
            raise ParseError("Формат: /move <id> <дата> <час>, напр. /move 12 20.11 14:00")
        bid = int(parts[0].lstrip("#"))
        d = parse_date(parts[1], _today(clock, settings))
        start = local_to_utc(d, parse_time(parts[2]), settings.zone)
        await asyncio.to_thread(
            bs.reschedule_booking,
            bid,
            start,
            now=clock(),
            engine=engine,
            tz=settings.zone,
            min_lead_min=0,
        )
    except bs.SlotTakenError:
        await message.answer("⚠️ Цей час зайнятий або поза графіком майстра")
        return
    except (ParseError, bs.BookingError) as e:
        await _reply_error(message, e)
        return
    status = await _notify_client_about(
        engine, notifier, bid, lambda s: f"Ваш запис перенесено: {s}. Чекаємо на вас!"
    )
    await message.answer(f"🔁 Запис #{bid} перенесено на {fmt_slot(start)}, {status}")


@router.message(Command("noshow", "done"))
async def cmd_mark(message: Message, command: CommandObject, engine: Engine) -> None:
    status = BookingStatus.no_show if command.command == "noshow" else BookingStatus.completed
    try:
        bid = _int_arg(command)
        await asyncio.to_thread(bs.set_status, bid, status, engine=engine)
    except (ParseError, bs.BookingError) as e:
        await _reply_error(message, e)
        return
    await message.answer(
        f"Запис #{bid}: {'неявка ❌' if status == BookingStatus.no_show else 'виконано ✅'}"
    )


@router.message(Command("dayoff"))
async def cmd_dayoff(
    message: Message, command: CommandObject, engine: Engine, settings: Settings, clock: Clock
) -> None:
    parts = (command.args or "").split()
    if len(parts) != 2:
        await _reply_error(message, ParseError("Формат: /dayoff <майстер> <дата>"))
        return
    try:
        d = parse_date(parts[1], _today(clock, settings))
    except ParseError as e:
        await _reply_error(message, e)
        return
    with Session(engine) as session, session.begin():
        master = q.find_master(session, parts[0])
        if master is None:
            await _reply_error(message, ParseError(f"Майстра «{parts[0]}» не знайдено"))
            return
        affected = q.set_day_off(session, master, d)
        lines = [f"🏖 {master.name}: вихідний {fmt_date_long(d)}. Бот не пропонуватиме слоти."]
        if affected:
            lines.append("⚠️ На цей день уже є записи — перенесіть або скасуйте:")
            lines += [
                f"  #{b.id} {fmt_slot(b.start_at)} {b.service.name} — {b.client.name}"
                for b in affected
            ]
    await message.answer("\n".join(lines))


# --- діалоги та handoff ----------------------------------------------------


def _set_conv_state(engine: Engine, conv_id: int, paused: bool) -> bool:
    with Session(engine) as session, session.begin():
        conv = session.get(Conversation, conv_id)
        if conv is None:
            return False
        (cl.pause if paused else cl.resume)(session, conv)
    return True


@router.message(Command("takeover", "resume"))
async def cmd_conv_state(message: Message, command: CommandObject, engine: Engine) -> None:
    try:
        cid = _int_arg(command)
    except ParseError as e:
        await _reply_error(message, e)
        return
    paused = command.command == "takeover"
    if not _set_conv_state(engine, cid, paused):
        await _reply_error(message, ParseError(f"Діалог #{cid} не знайдено"))
        return
    await message.answer(
        f"🙋 Діалог #{cid} ваш, AI мовчить. Відповідати: /reply {cid} текст"
        if paused
        else f"🤖 Діалог #{cid} повернуто AI"
    )


@router.callback_query(ConvCb.filter())
async def on_conv_button(cb: CallbackQuery, callback_data: ConvCb, engine: Engine) -> None:
    paused = callback_data.a == "takeover"
    ok = _set_conv_state(engine, callback_data.id, paused)
    who = cb.from_user.first_name
    await cb.answer("Готово" if ok else "Діалог не знайдено")
    if ok and cb.message:
        await cb.message.answer(
            f"🙋 {who} перехопив(-ла) діалог #{callback_data.id}. /reply {callback_data.id} текст"
            if paused
            else f"🤖 Діалог #{callback_data.id} повернуто AI"
        )


@router.message(Command("reply"))
async def cmd_reply(
    message: Message, command: CommandObject, engine: Engine, notifier: Notifier
) -> None:
    parts = (command.args or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[0].lstrip("#").isdigit():
        await _reply_error(message, ParseError("Формат: /reply <діалог> <текст>"))
        return
    cid, text = int(parts[0].lstrip("#")), parts[1]
    with Session(engine) as session:
        conv = session.get(Conversation, cid)
        if conv is None:
            await _reply_error(message, ParseError(f"Діалог #{cid} не знайдено"))
            return
        client = session.get(Client, conv.client_id)
        target = notifier.client_channel(session, client)
        channel = conv.channel
    if target is None or target[0] != channel:
        await message.answer(
            "⚠️ Канал закритий (у Instagram минуло 24 год). Напишіть клієнту напряму."
        )
        return
    if not await notifier.send_to_channel(target[0], target[1], text):
        await message.answer("⚠️ Не вдалося надіслати")
        return
    with Session(engine) as session, session.begin():
        conv = session.get(Conversation, cid)
        cl.add_message(session, conv, MessageRole.admin, text)
        cl.pause(session, conv)  # адмін веде діалог → AI мовчить
    await message.answer(f"✉️ Надіслано в діалог #{cid}")


@router.message(Command("pause_all", "resume_all"))
async def cmd_global_pause(message: Message, command: CommandObject, engine: Engine) -> None:
    paused = command.command == "pause_all"
    with Session(engine) as session, session.begin():
        cl.set_ai_globally_paused(session, paused)
    await message.answer(
        "⏸ AI вимкнено на всіх каналах. Увімкнути: /resume_all"
        if paused
        else "▶️ AI знову відповідає"
    )


# --- прайс, статистика, клієнти --------------------------------------------


@router.message(Command("price"))
async def cmd_price(message: Message, engine: Engine) -> None:
    with Session(engine) as session:
        text = q.price_list(session, html=True)
        kb = InlineKeyboardBuilder()
        for s in session.scalars(
            select(Service).where(Service.is_active.is_(True)).order_by(Service.name)
        ):
            kb.button(text=f"✏️ {s.name}", callback_data=PriceCb(id=s.id))
        kb.adjust(1)
    await message.answer(
        text + "\n\nЗмінити ціну — кнопка нижче:", reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@router.callback_query(PriceCb.filter())
async def on_price_edit(
    cb: CallbackQuery, callback_data: PriceCb, state: FSMContext, engine: Engine
) -> None:
    with Session(engine) as session:
        s = session.get(Service, callback_data.id)
        name = s.name if s else None
    await cb.answer()
    if name is None:
        return
    await state.set_state(PriceEdit.value)
    await state.update_data(service_id=callback_data.id)
    await cb.message.answer(f"Нова ціна для «{name}»: число або діапазон (600 або 600-800)")


@router.message(PriceEdit.value, F.text)
async def on_price_value(message: Message, state: FSMContext, engine: Engine) -> None:
    try:
        price_from, price_to = q.parse_price(message.text)
    except ValueError as e:
        await _reply_error(message, e)
        return
    data = await state.get_data()
    await state.clear()
    with Session(engine) as session, session.begin():
        s = session.get(Service, data["service_id"])
        s.price_from, s.price_to = price_from, price_to
        name = s.name
    await message.answer(f"💰 «{name}»: {message.text.strip()} грн")


@router.message(Command("stats"))
async def cmd_stats(message: Message, engine: Engine, clock: Clock, usage: Any = None) -> None:
    now = clock()
    with Session(engine) as session:
        stats = q.weekly_stats(session, now)
        cost = usage.cost_since(session, now - timedelta(days=7)) if usage else None
    await message.answer(q.format_stats(stats, cost))


def _find_client(session: Session, arg: str) -> Client | None:
    arg = arg.strip()
    if arg.lstrip("#").isdigit() and len(arg.lstrip("#")) < 7:
        return session.get(Client, int(arg.lstrip("#")))
    phone = normalize_phone(arg)
    return cl.find_client_by_phone(session, phone) if phone else None


@router.message(Command("client"))
async def cmd_client(
    message: Message, command: CommandObject, engine: Engine, clock: Clock
) -> None:
    if not command.args:
        await _reply_error(message, ParseError("Формат: /client <телефон або id>"))
        return
    with Session(engine) as session:
        client = _find_client(session, command.args)
        if client is None:
            await message.answer("Клієнта не знайдено")
            return
        await message.answer(q.client_card(session, client, clock()))


@router.message(Command("forget"))
async def cmd_forget(message: Message, command: CommandObject, engine: Engine) -> None:
    phone = normalize_phone(command.args or "")
    if phone is None:
        await _reply_error(message, ParseError("Формат: /forget <телефон>"))
        return
    with Session(engine) as session, session.begin():
        client = cl.find_client_by_phone(session, phone)
        if client is None:
            await message.answer("Клієнта з таким телефоном немає")
            return
        cl.forget_client(session, client)
    await message.answer("🗑 Клієнта і всю його історію видалено")
