import asyncio
import html
import logging
import os
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
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

# ==========================================================
# Studio Booking Bot 24/7 (UA / PL) — Portfolio Demo OK GER
# ==========================================================

BOT_TOKEN = os.getenv("BOOKING_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID", "123456789"))
DB_PATH = os.getenv("BOOKING_DB_PATH", "bookings.db")

logging.basicConfig(level=logging.INFO)
router = Router()


class BookingStates(StatesGroup):
    choosing_lang = State()
    choosing_service = State()
    choosing_day = State()
    sharing_contact = State()


TEXTS = {
    "ua": {
        "lang_set": "🇺🇦 Обрано українську мову.",
        "welcome": (
            "👋 <b>Вітаємо у Studio Booking Bot 24/7!</b>\n\n"
            "Оберіть потрібну послугу нижче, щоб записатися за 30 секунд:"
        ),
        "services": [
            "✂️ Чоловіча стрижка • 80 zł",
            "🧔 Стрижка + борода • 110 zł",
            "🔥 Комплекс VIP • 150 zł",
        ],
        "ask_day": "📅 Оберіть зручний день візиту:",
        "days": ["Сьогодні", "Завтра", "У вихідні"],
        "ask_phone": (
            "📱 Натисніть кнопку нижче, щоб поділитися номером в 1 дотик,\n"
            "або введіть телефон вручну (напр. <code>+48 512 345 678</code>):"
        ),
        "share_btn": "📱 Поділитися номером телефону",
        "cancel_btn": "❌ Скасувати",
        "cancelled": "Запис скасовано. Натисніть /start, щоб почати знову.",
        "invalid_phone": "⚠️ Введіть коректний номер телефону (мінімум 9 цифр) або натисніть кнопку нижче.",
        "client_ok": (
            "✅ <b>Запис #{booking_id} підтверджено!</b>\n\n"
            "🛠 Послуга: <b>{service}</b>\n"
            "⏰ День: <b>{day}</b>\n"
            "📞 Телефон: <code>{phone}</code>\n\n"
            "Адміністратор зв'яжеться з вами для уточнення точного часу. Чекаємо на вас!"
        ),
        "again_btn": "🔄 Записатися ще раз",
        "change_lang_btn": "🌐 Змінити мову (UA / PL)",
    },
    "pl": {
        "lang_set": "🇵🇱 Wybrano język polski.",
        "welcome": (
            "👋 <b>Witamy w Studio Booking Bot 24/7!</b>\n\n"
            "Wybierz usługę poniżej, aby umówić wizytę w 30 sekund:"
        ),
        "services": [
            "✂️ Strzyżenie męskie • 80 zł",
            "🧔 Strzyżenie + broda • 110 zł",
            "🔥 Pakiet VIP • 150 zł",
        ],
        "ask_day": "📅 Wybierz dogodny dzień wizyty:",
        "days": ["Dziś", "Jutro", "W weekend"],
        "ask_phone": (
            "📱 Kliknij przycisk poniżej, aby udostępnić numer jednym dotykiem,\n"
            "lub wpisz numer ręcznie (np. <code>+48 512 345 678</code>):"
        ),
        "share_btn": "📱 Udostępnij numer telefonu",
        "cancel_btn": "❌ Anuluj",
        "cancelled": "Rezerwacja anulowana. Kliknij /start, aby zacząć od nowa.",
        "invalid_phone": "⚠️ Podaj poprawny numer telefonu (min. 9 cyfr) lub użyj przycisku poniżej.",
        "client_ok": (
            "✅ <b>Rezerwacja #{booking_id} przyjęta!</b>\n\n"
            "🛠 Usługa: <b>{service}</b>\n"
            "⏰ Termin: <b>{day}</b>\n"
            "📞 Telefon: <code>{phone}</code>\n\n"
            "Administrator potwierdzi dokładną godzinę wizyty. Do zobaczenia!"
        ),
        "again_btn": "🔄 Umów kolejną wizytę",
        "change_lang_btn": "🌐 Zmień język (UA / PL)",
    },
}


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                full_name TEXT,
                lang TEXT NOT NULL,
                service TEXT NOT NULL,
                visit_day TEXT NOT NULL,
                phone TEXT NOT NULL,
                status TEXT DEFAULT 'new',
                created_at TEXT NOT NULL
            )
            """
        )


def save_booking(
    user_id: int,
    username: str,
    full_name: str,
    lang: str,
    service: str,
    visit_day: str,
    phone: str,
) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """
            INSERT INTO bookings (user_id, username, full_name, lang, service, visit_day, phone, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                username,
                full_name,
                lang,
                service,
                visit_day,
                phone,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            ),
        )
        return cur.lastrowid


def update_booking_status(booking_id: int, status: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE bookings SET status = ? WHERE id = ?", (status, booking_id))


def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang:ua"),
                InlineKeyboardButton(text="🇵🇱 Polski", callback_data="lang:pl"),
            ]
        ]
    )


def services_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=srv, callback_data=f"srv:{idx}")]
        for idx, srv in enumerate(TEXTS[lang]["services"])
    ]
    rows.append(
        [InlineKeyboardButton(text=TEXTS[lang]["change_lang_btn"], callback_data="change_lang")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def days_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=d, callback_data=f"day:{idx}")]
        for idx, d in enumerate(TEXTS[lang]["days"])
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def contact_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TEXTS[lang]["share_btn"], request_contact=True)],
            [KeyboardButton(text=TEXTS[lang]["cancel_btn"])],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


@router.message(CommandStart())
@router.message(Command("lang"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BookingStates.choosing_lang)
    await message.answer(
        "🇺🇦 Оберіть мову / 🇵🇱 Wybierz język:",
        reply_markup=lang_keyboard(),
    )


@router.callback_query(F.data == "change_lang")
async def cb_change_lang(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BookingStates.choosing_lang)
    await callback.message.edit_text(
        "🇺🇦 Оберіть мову / 🇵🇱 Wybierz język:",
        reply_markup=lang_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lang:"))
async def cb_set_lang(callback: CallbackQuery, state: FSMContext) -> None:
    lang = callback.data.split(":", 1)[1]
    await state.update_data(lang=lang)
    await state.set_state(BookingStates.choosing_service)
    await callback.message.edit_text(
        TEXTS[lang]["welcome"],
        reply_markup=services_keyboard(lang),
    )
    await callback.answer(TEXTS[lang]["lang_set"])


@router.callback_query(BookingStates.choosing_service, F.data.startswith("srv:"))
async def cb_pick_service(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ua")
    idx = int(callback.data.split(":", 1)[1])
    service = TEXTS[lang]["services"][idx]

    await state.update_data(service=service)
    await state.set_state(BookingStates.choosing_day)
    await callback.message.edit_text(
        f"✅ <b>{html.escape(service)}</b>\n\n{TEXTS[lang]['ask_day']}",
        reply_markup=days_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(BookingStates.choosing_day, F.data.startswith("day:"))
async def cb_pick_day(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ua")
    idx = int(callback.data.split(":", 1)[1])
    day = TEXTS[lang]["days"][idx]

    await state.update_data(day=day)
    await state.set_state(BookingStates.sharing_contact)
    await callback.message.delete()
    await callback.message.answer(
        TEXTS[lang]["ask_phone"],
        reply_markup=contact_keyboard(lang),
    )
    await callback.answer()


@router.message(BookingStates.sharing_contact, F.text.in_({"❌ Скасувати", "❌ Anuluj"}))
async def msg_cancel_booking(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ua")
    await state.clear()
    await message.answer(TEXTS[lang]["cancelled"], reply_markup=ReplyKeyboardRemove())


@router.message(BookingStates.sharing_contact, F.contact)
async def msg_contact_shared(message: Message, state: FSMContext, bot: Bot) -> None:
    phone = message.contact.phone_number
    if not phone.startswith("+"):
        phone = f"+{phone}"
    await finalize_booking(message, state, bot, phone)


@router.message(BookingStates.sharing_contact, F.text)
async def msg_phone_typed(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ua")
    raw = message.text.strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) < 9:
        await message.answer(TEXTS[lang]["invalid_phone"])
        return
    await finalize_booking(message, state, bot, raw)


async def finalize_booking(
    message: Message,
    state: FSMContext,
    bot: Bot,
    phone: str,
) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ua")
    service = data.get("service", "—")
    day = data.get("day", "—")

    user = message.from_user
    username = f"@{user.username}" if user and user.username else "немає username"
    full_name = html.escape(user.full_name) if user else "Клієнт"

    booking_id = save_booking(
        user_id=user.id if user else 0,
        username=username,
        full_name=full_name,
        lang=lang,
        service=service,
        visit_day=day,
        phone=phone,
    )

    again_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=TEXTS[lang]["again_btn"], callback_data=f"lang:{lang}")]
        ]
    )

    await message.answer(
        TEXTS[lang]["client_ok"].format(
            booking_id=booking_id,
            service=html.escape(service),
            day=html.escape(day),
            phone=html.escape(phone),
        ),
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("👇", reply_markup=again_kb)

    owner_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Підтвердити візит",
                    callback_data=f"admin:confirm:{booking_id}:{user.id}",
                ),
                InlineKeyboardButton(
                    text="❌ Скасувати",
                    callback_data=f"admin:cancel:{booking_id}:{user.id}",
                ),
            ]
        ]
    )

    owner_text = (
        f"🆕 <b>НОВИЙ ЗАПИС #{booking_id} ІЗ БОТА</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Клієнт: <b>{full_name}</b> ({html.escape(username)})\n"
        f"📞 Телефон: <code>{html.escape(phone)}</code>\n"
        f"🛠 Послуга: <b>{html.escape(service)}</b>\n"
        f"⏰ День: <b>{html.escape(day)}</b>\n"
        f"🌐 Мова клієнта: <b>{lang.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    try:
        await bot.send_message(chat_id=OWNER_CHAT_ID, text=owner_text, reply_markup=owner_kb)
    except Exception as exc:
        logging.warning("Не вдалося надіслати заявку власнику (%s): %s", OWNER_CHAT_ID, exc)

    await state.clear()


@router.callback_query(F.data.startswith("admin:"))
async def cb_admin_action(callback: CallbackQuery, bot: Bot) -> None:
    _, action, booking_id_str, client_id_str = callback.data.split(":")
    booking_id = int(booking_id_str)
    client_id = int(client_id_str)

    if action == "confirm":
        update_booking_status(booking_id, "confirmed")
        status_badge = "\n\n🟢 <b>Статус: Підтверджено адміністратором</b>"
        client_notice = f"✅ Ваш запис <b>#{booking_id}</b> підтверджено адміністратором! Чекаємо на вас."
    else:
        update_booking_status(booking_id, "cancelled")
        status_badge = "\n\n🔴 <b>Статус: Скасовано адміністратором</b>"
        client_notice = f"⚠️ На жаль, запис <b>#{booking_id}</b> скасовано. Напишіть нам, щоб підібрати інший час."

    await callback.message.edit_text(callback.message.html_text + status_badge)
    try:
        await bot.send_message(chat_id=client_id, text=client_notice)
    except Exception:
        pass
    await callback.answer("Статус оновлено")


@router.message(Command("leads"))
async def cmd_leads(message: Message) -> None:
    if message.from_user and message.from_user.id != OWNER_CHAT_ID:
        return
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, full_name, phone, service, visit_day, status, created_at FROM bookings ORDER BY id DESC LIMIT 10"
        ).fetchall()

    if not rows:
        await message.answer("📭 Поки що записів немає.")
        return

    lines = ["📋 <b>Останні 10 записів із бота:</b>\n"]
    for r in rows:
        lines.append(
            f"#{r[0]} • {html.escape(r[1])} (<code>{html.escape(r[2])}</code>) — "
            f"{html.escape(r[3])} [{r[4]}] ({r[5]})"
        )
    await message.answer("\n".join(lines))


async def main() -> None:
    init_db()
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
