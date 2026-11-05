"""Telegram: клієнтський бот (aiogram 3) і покроковий запис кнопками.

Покроковий запис спільний для клієнта (/book у приватному чаті) і адміна
(/book в адмін-групі, mode="admin": без мінімального запасу часу, телефон обов'язковий).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import clients as cl
from app.agent.usage import UsageReport
from app.booking import service as bs
from app.channels.registry import HandlerRegistry
from app.config import Settings
from app.db.models import (
    Booking,
    BookingStatus,
    Channel,
    Client,
    Conversation,
    Master,
    MasterService,
    Service,
)
from app.notify import Notifier
from app.text import fmt_price, fmt_slot, normalize_phone

log = logging.getLogger(__name__)

GREETING = (
    "Привіт! Я AI-помічник салону M&D 🤖\n"
    "Можу записати вас до майстра, розповісти про послуги й ціни "
    "або покликати адміністратора.\n\n"
    "/book — записатися\n/my — мої записи\n\nАбо просто напишіть, що вас цікавить."
)
SLOTS_WINDOW_DAYS = 14

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(UTC)


class BookCb(CallbackData, prefix="bk"):
    a: str  # svc | mst | slot | more | ok | no | skip
    v: int = 0
    m: int = 0


class MyCb(CallbackData, prefix="my"):
    a: str  # cancel
    id: int


class BookFlow(StatesGroup):
    choosing = State()
    name = State()
    phone = State()
    confirm = State()


# --- покроковий запис ---------------------------------------------------------

router = HandlerRegistry("booking")


def _services_kb(session: Session) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    services = session.scalars(
        select(Service)
        .join(MasterService, MasterService.service_id == Service.id)
        .where(Service.is_active.is_(True))
        .distinct()
        .order_by(Service.category, Service.name)
    )
    for s in services:
        kb.button(
            text=f"{s.name} · {fmt_price(s.price_from, s.price_to)}",
            callback_data=BookCb(a="svc", v=s.id),
        )
    kb.button(text="✖️ Скасувати", callback_data=BookCb(a="no"))
    kb.adjust(1)
    return kb.as_markup()


async def start_booking(
    message: Message, state: FSMContext, engine: Engine, mode: str = "client"
) -> None:
    await state.clear()
    await state.set_state(BookFlow.choosing)
    await state.update_data(mode=mode)
    with Session(engine) as session:
        kb = _services_kb(session)
    await message.answer("Оберіть послугу:", reply_markup=kb)


def _lead(mode: str, settings: Settings) -> int:
    return 0 if mode == "admin" else settings.min_lead_min


async def _show_slots(
    target: Message,
    state: FSMContext,
    engine: Engine,
    settings: Settings,
    clock: Clock,
    date_from: date | None = None,
    note: str = "",
) -> None:
    data = await state.get_data()
    now = clock()
    today = now.astimezone(settings.zone).date()
    date_from = max(date_from or today, today)
    with Session(engine) as session:
        service = session.get(Service, data["service_id"])
        slots = bs.find_free_slots(
            session,
            data["service_id"],
            date_from,
            date_from + timedelta(days=SLOTS_WINDOW_DAYS - 1),
            master_id=data.get("master_id") or None,
            now=now,
            tz=settings.zone,
            min_lead_min=_lead(data["mode"], settings),
            step_min=settings.slot_step_min,
            max_slots=settings.max_slots,
        )
        names = dict(session.execute(select(Master.id, Master.name)).all())
    kb = InlineKeyboardBuilder()
    for s in slots:
        mid = s.master_ids[0]
        label = fmt_slot(s.start_at, settings.zone)
        if not data.get("master_id"):
            label += f" · {names[mid]}"
        kb.button(text=label, callback_data=BookCb(a="slot", v=int(s.start_at.timestamp()), m=mid))
    next_from = (
        slots[-1].start_at.astimezone(settings.zone).date() + timedelta(days=1)
        if slots
        else date_from + timedelta(days=SLOTS_WINDOW_DAYS)
    )
    kb.button(text="Пізніші дати ➡️", callback_data=BookCb(a="more", v=next_from.toordinal()))
    kb.button(text="✖️ Скасувати", callback_data=BookCb(a="no"))
    kb.adjust(1)
    head = f"{note}\n\n" if note else ""
    if slots:
        text = f"{head}{service.name}. Оберіть час:"
    else:
        text = (
            f"{head}{service.name}: на ці дні вільних вікон немає. "
            "Подивіться пізніші дати або напишіть, і адміністратор підбере час."
        )
    try:
        await target.edit_text(text, reply_markup=kb.as_markup())
    except Exception:  # повідомлення не можна редагувати (напр., воно від клієнта)
        await target.answer(text, reply_markup=kb.as_markup())


@router.callback_query(BookFlow.choosing, BookCb.filter(F.a == "svc"))
async def on_service(
    cb: CallbackQuery, callback_data: BookCb, state: FSMContext, engine: Engine,
    settings: Settings, clock: Clock,
) -> None:  # fmt: skip
    await state.update_data(service_id=callback_data.v, master_id=None)
    with Session(engine) as session:
        masters = list(
            session.scalars(
                select(Master)
                .join(MasterService, MasterService.master_id == Master.id)
                .where(MasterService.service_id == callback_data.v, Master.is_active.is_(True))
                .order_by(Master.id)
            )
        )
    await cb.answer()
    if len(masters) == 1:
        await state.update_data(master_id=masters[0].id)
        await _show_slots(cb.message, state, engine, settings, clock)
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="Будь-який майстер", callback_data=BookCb(a="mst", v=0))
    for m in masters:
        kb.button(text=m.name, callback_data=BookCb(a="mst", v=m.id))
    kb.button(text="✖️ Скасувати", callback_data=BookCb(a="no"))
    kb.adjust(1)
    await cb.message.edit_text("До якого майстра?", reply_markup=kb.as_markup())


@router.callback_query(BookFlow.choosing, BookCb.filter(F.a == "mst"))
async def on_master(
    cb: CallbackQuery, callback_data: BookCb, state: FSMContext, engine: Engine,
    settings: Settings, clock: Clock,
) -> None:  # fmt: skip
    await state.update_data(master_id=callback_data.v or None)
    await cb.answer()
    await _show_slots(cb.message, state, engine, settings, clock)


@router.callback_query(BookFlow.choosing, BookCb.filter(F.a == "more"))
async def on_more(
    cb: CallbackQuery, callback_data: BookCb, state: FSMContext, engine: Engine,
    settings: Settings, clock: Clock,
) -> None:  # fmt: skip
    await cb.answer()
    await _show_slots(cb.message, state, engine, settings, clock, date.fromordinal(callback_data.v))


def _phone_kb(required: bool) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text="📱 Надіслати мій номер", request_contact=True)]]
    if not required:
        rows.append([KeyboardButton(text="Пропустити")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


@router.callback_query(BookFlow.choosing, BookCb.filter(F.a == "slot"))
async def on_slot(
    cb: CallbackQuery, callback_data: BookCb, state: FSMContext, engine: Engine
) -> None:
    await state.update_data(start_ts=callback_data.v, master_id=callback_data.m)
    data = await state.get_data()
    await cb.answer()
    if data["mode"] == "admin":
        await state.set_state(BookFlow.name)
        await cb.message.edit_text("Ім'я клієнта?")
        return
    with Session(engine) as session:
        client = cl.get_or_create_tg_client(session, cb.from_user.id, "")
        name, phone = client.name, client.phone
        session.commit()
    if not name:
        await state.set_state(BookFlow.name)
        await cb.message.edit_text("Як до вас звертатися?")
        return
    await state.update_data(name=name)
    if not phone:
        await state.set_state(BookFlow.phone)
        await cb.message.delete()
        await cb.message.answer(
            "Залиште, будь ласка, номер телефону — на випадок, якщо треба буде щось уточнити.",
            reply_markup=_phone_kb(required=False),
        )
        return
    await state.update_data(phone=phone)
    await _ask_confirm(cb.message, state, engine, edit=True)


@router.message(BookFlow.name, F.text)
async def on_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()[:100]
    if not name or name.startswith("/"):
        await message.answer("Напишіть ім'я текстом 🙂")
        return
    await state.update_data(name=name)
    data = await state.get_data()
    await state.set_state(BookFlow.phone)
    if data["mode"] == "admin":
        await message.answer("Телефон клієнта?")
    else:
        await message.answer(
            "Дякую! Залиште номер телефону — на випадок, якщо треба буде щось уточнити.",
            reply_markup=_phone_kb(required=False),
        )


@router.message(BookFlow.phone)
async def on_phone(message: Message, state: FSMContext, engine: Engine) -> None:
    data = await state.get_data()
    raw = message.contact.phone_number if message.contact else (message.text or "")
    if data["mode"] != "admin" and raw.strip().lower() == "пропустити":
        await state.update_data(phone=None)
    else:
        phone = normalize_phone(raw)
        if phone is None:
            await message.answer("Не схоже на номер. Приклад: 067 123 45 67")
            return
        await state.update_data(phone=phone)
    await _ask_confirm(message, state, engine)


async def _ask_confirm(
    message: Message, state: FSMContext, engine: Engine, edit: bool = False
) -> None:
    data = await state.get_data()
    await state.set_state(BookFlow.confirm)
    with Session(engine) as session:
        service = session.get(Service, data["service_id"])
        master = session.get(Master, data["master_id"])
    start = datetime.fromtimestamp(data["start_ts"], UTC)
    text = (
        "Перевірте, будь ласка:\n"
        f"• {service.name} ({fmt_price(service.price_from, service.price_to)})\n"
        f"• Майстер: {master.name}\n"
        f"• {fmt_slot(start)}\n"
        f"• {data['name']}" + (f", {data['phone']}" if data.get("phone") else "") + "\n\n"
        "Записуємо?"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Так", callback_data=BookCb(a="ok"))
    kb.button(text="↩️ Інший час", callback_data=BookCb(a="more", v=0))
    kb.button(text="✖️ Скасувати", callback_data=BookCb(a="no"))
    kb.adjust(1)
    if edit:
        await message.edit_text(text, reply_markup=kb.as_markup())
    else:
        await message.answer("👌", reply_markup=ReplyKeyboardRemove())
        await message.answer(text, reply_markup=kb.as_markup())


@router.callback_query(BookFlow.confirm, BookCb.filter(F.a == "more"))
async def on_other_time(
    cb: CallbackQuery, state: FSMContext, engine: Engine, settings: Settings, clock: Clock
) -> None:
    await state.set_state(BookFlow.choosing)
    await cb.answer()
    await _show_slots(cb.message, state, engine, settings, clock)


def _resolve_client(session: Session, data: dict[str, Any], tg_user_id: int) -> Client:
    phone = data.get("phone")
    if data["mode"] == "admin":
        client = cl.find_client_by_phone(session, phone) if phone else None
        if client is None:
            client = Client(name=data["name"], phone=phone)
            session.add(client)
            session.flush()
        elif not client.name:
            client.name = data["name"]
        return client
    client = cl.get_or_create_tg_client(session, tg_user_id)
    client.name = data["name"]
    if phone:
        client = cl.attach_phone(session, client, phone)
    return client


@router.callback_query(BookFlow.confirm, BookCb.filter(F.a == "ok"))
async def on_confirm(
    cb: CallbackQuery, state: FSMContext, engine: Engine, settings: Settings,
    notifier: Notifier, clock: Clock,
) -> None:  # fmt: skip
    data = await state.get_data()
    with Session(engine, expire_on_commit=False) as session, session.begin():
        client = _resolve_client(session, data, cb.from_user.id)
        client_id = client.id
    admin = data["mode"] == "admin"
    try:
        booking = await asyncio.to_thread(
            bs.create_booking,
            service_id=data["service_id"],
            master_id=data["master_id"],
            start_at=datetime.fromtimestamp(data["start_ts"], UTC),
            client_id=client_id,
            source=Channel.admin if admin else Channel.telegram,
            created_by=str(cb.from_user.id) if admin else "client",
            now=clock(),
            engine=engine,
            tz=settings.zone,
            min_lead_min=_lead(data["mode"], settings),
        )
    except bs.SlotTakenError:
        await cb.answer("Цей час щойно зайняли")
        await state.set_state(BookFlow.choosing)
        await _show_slots(
            cb.message, state, engine, settings, clock, note="😔 Цей час щойно зайняли."
        )
        return
    except bs.BookingError as e:
        await cb.answer()
        await state.clear()
        await cb.message.edit_text(f"Не вдалося записати: {e}")
        return
    await state.clear()
    await cb.answer("Записано!")
    summary = await announce_booking(engine, notifier, booking.id)
    if admin:
        await cb.message.edit_text(f"✅ Записано #{booking.id}: {summary}")
    else:
        await cb.message.edit_text(
            f"✅ Готово! {summary}.\nНагадаємо за день і за 2 години до візиту. "
            "Якщо плани зміняться — напишіть сюди."
        )


@router.callback_query(BookCb.filter(F.a == "no"))
async def on_abort(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.answer()
    await cb.message.edit_text("Добре, скасовано. Якщо що — /book")


async def announce_booking(engine: Engine, notifier: Notifier, booking_id: int) -> str:
    """Сповіщення в адмін-групу про новий запис. Повертає короткий підсумок."""
    from app.admin.queries import booking_summary, load_booking

    with Session(engine) as session:
        b = load_booking(session, booking_id)
        summary = booking_summary(b)
        source = b.source
    await notifier.admin(f"🆕 Новий запис #{booking_id} ({source.value}): {summary}")
    return summary


# --- клієнтські команди ------------------------------------------------------

client_router = HandlerRegistry("client")
client_router.filter("message", F.chat.type == "private")


@client_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, engine: Engine) -> None:
    await state.clear()
    with Session(engine) as session, session.begin():
        client = cl.get_or_create_tg_client(
            session, message.from_user.id, message.from_user.first_name
        )
        conv = cl.get_conversation(session, client.id, Channel.telegram)
        # Привітання вже каже, що це AI-помічник → у першій AI-відповіді не повторюємо.
        cl.add_message(session, conv, cl.MessageRole.assistant, GREETING)
    await message.answer(GREETING, reply_markup=ReplyKeyboardRemove())


@client_router.message(Command("book"))
async def cmd_book(message: Message, state: FSMContext, engine: Engine) -> None:
    await start_booking(message, state, engine, mode="client")


@client_router.message(Command("my"))
async def cmd_my(message: Message, engine: Engine, clock: Clock) -> None:
    with Session(engine) as session:
        client = session.scalar(select(Client).where(Client.tg_user_id == message.from_user.id))
        bookings = (
            list(
                session.scalars(
                    select(Booking)
                    .where(
                        Booking.client_id == client.id,
                        Booking.status == BookingStatus.confirmed,
                        Booking.start_at >= clock(),
                    )
                    .order_by(Booking.start_at)
                )
            )
            if client
            else []
        )
        lines = [
            (b.id, f"{fmt_slot(b.start_at)} — {b.service.name}, {b.master.name}") for b in bookings
        ]
    if not lines:
        await message.answer("Майбутніх записів немає. Записатися — /book")
        return
    kb = InlineKeyboardBuilder()
    for bid, line in lines:
        kb.button(text=f"✖️ Скасувати: {line}", callback_data=MyCb(a="cancel", id=bid))
    kb.adjust(1)
    await message.answer(
        "Ваші записи:\n" + "\n".join(f"• {line}" for _, line in lines), reply_markup=kb.as_markup()
    )


@client_router.callback_query(MyCb.filter(F.a == "cancel"))
async def on_my_cancel(
    cb: CallbackQuery, callback_data: MyCb, engine: Engine, notifier: Notifier
) -> None:
    from app.admin.queries import booking_summary, load_booking

    with Session(engine) as session:
        b = load_booking(session, callback_data.id)
        if b is None or b.client.tg_user_id != cb.from_user.id:
            await cb.answer("Запис не знайдено", show_alert=True)
            return
        summary = booking_summary(b)
    try:
        await asyncio.to_thread(
            bs.set_status, callback_data.id, BookingStatus.cancelled, engine=engine
        )
    except bs.BookingError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer("Скасовано")
    await cb.message.edit_text(f"Запис скасовано: {summary}. Записатися знову — /book")
    await notifier.admin(f"🚫 Клієнт скасував #{callback_data.id}: {summary}")


@client_router.message(F.text)
async def on_free_text(
    message: Message, engine: Engine, notifier: Notifier, dialog: Any = None
) -> None:
    """Вільний текст → AI-агент (етап 4). Без агента — підказка і сповіщення адміну."""
    if dialog is not None:
        await dialog.handle_telegram(message)
        return
    with Session(engine) as session, session.begin():
        client = cl.get_or_create_tg_client(
            session, message.from_user.id, message.from_user.first_name
        )
        conv = cl.get_conversation(session, client.id, Channel.telegram)
        cl.add_message(session, conv, cl.MessageRole.client, message.text)
        conv_id = conv.id
    await message.answer("Дякую! Адміністратор скоро відповість. Записатися самостійно — /book")
    await notifier.admin(f"💬 Нове повідомлення в Telegram, діалог #{conv_id}")


# --- збірка ------------------------------------------------------------------


def telegram_sender(bot: Bot) -> Callable[[str, str], Any]:
    async def send(recipient_id: str, text: str) -> bool:
        await bot.send_message(int(recipient_id), text)
        return True

    return send


def admin_sender(bot: Bot, chat_id: int) -> Callable[..., Any]:
    async def send(text: str, keyboard: Any | None = None) -> None:
        if chat_id:
            await bot.send_message(chat_id, text, reply_markup=keyboard)

    return send


def conversation_keyboard(conv: Conversation, client: Client) -> InlineKeyboardMarkup:
    """Кнопки до сповіщення: «Відкрити діалог», «Перехопити»."""
    from app.admin.commands import ConvCb

    rows = []
    if conv.channel == Channel.telegram and client.tg_user_id:
        rows.append(
            [InlineKeyboardButton(text="Відкрити діалог", url=f"tg://user?id={client.tg_user_id}")]
        )
    elif conv.channel == Channel.instagram:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Відкрити Direct", url="https://www.instagram.com/direct/inbox/"
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="Перехопити", callback_data=ConvCb(a="takeover", id=conv.id).pack()
            ),
            InlineKeyboardButton(
                text="Повернути AI", callback_data=ConvCb(a="resume", id=conv.id).pack()
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_dispatcher(
    engine: Engine,
    settings: Settings,
    notifier: Notifier,
    *,
    dialog: Any = None,
    clock: Clock = utcnow,
) -> Dispatcher:
    from app.admin.commands import router as admin_router

    dp = Dispatcher(storage=MemoryStorage())
    dp["engine"] = engine
    dp["settings"] = settings
    dp["notifier"] = notifier
    dp["dialog"] = dialog
    dp["clock"] = clock
    dp["usage"] = UsageReport()
    dp.include_router(admin_router.build())
    dp.include_router(router.build())
    dp.include_router(client_router.build())
    return dp
