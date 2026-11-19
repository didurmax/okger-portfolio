import asyncio
import html
import logging
import os

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
# Service Estimator Bot (UA / PL) — Portfolio Demo OK GER
# ==========================================================

BOT_TOKEN = os.getenv("ESTIMATOR_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID", "123456789"))

logging.basicConfig(level=logging.INFO)
router = Router()


class EstimateStates(StatesGroup):
    choosing_service = State()
    entering_device_or_car = State()
    sharing_contact = State()


CATALOG = {
    "ua": {
        "welcome": (
            "🧮 <b>Service Estimator Bot — Онлайн-оцінка вартості</b>\n\n"
            "Оберіть послугу, щоб миттєво дізнатися орієнтовну ціну та час виконання:"
        ),
        "items": [
            {"name": "📱 Заміна екрана", "price": "від 249 zł (45 хв)", "ask_detail": "Вкажіть модель телефону (напр. iPhone 14 Pro або Samsung S23):"},
            {"name": "🔋 Заміна батареї", "price": "від 149 zł (30 хв)", "ask_detail": "Вкажіть модель пристрою (напр. iPhone 13 / MacBook Air M1):"},
            {"name": "🔍 Діагностика OBD / огляд", "price": "100 zł (30 хв)", "ask_detail": "Вкажіть марку, модель та рік авто (напр. Audi A4 B9 2018):"},
            {"name": "🛠 Заміна масла та фільтрів", "price": "від 120 zł (60 хв)", "ask_detail": "Вкажіть марку, модель та об'єм двигуна авто:"},
        ],
        "quote_msg": (
            "💰 Орієнтовна вартість: <b>{price}</b>\n"
            "📌 Пристрій / авто: <b>{detail}</b>\n\n"
            "Натисніть кнопку нижче, щоб зафіксувати ціну та передати заявку майстру:"
        ),
        "share_btn": "📞 Надіслати номер телефону",
        "cancel_btn": "❌ Скасувати",
        "cancelled": "Розрахунок скасовано. Натисніть /start для нового прорахунку.",
        "done_msg": (
            "✅ <b>Розрахунок зафіксовано!</b>\n\n"
            "🛠 Послуга: <b>{service}</b>\n"
            "📌 Модель / авто: <b>{detail}</b>\n"
            "💰 Оцінка: <b>{price}</b>\n"
            "📞 Ваш контакт: <code>{phone}</code>\n\n"
            "Майстер зв'яжеться з вами протягом 10 хвилин."
        ),
        "again_btn": "🔄 Розрахувати іншу послугу",
    },
    "pl": {
        "welcome": (
            "🧮 <b>Service Estimator Bot — Wycena usług online</b>\n\n"
            "Wybierz usługę, aby obliczyć szacunkowy koszt i czas realizacji:"
        ),
        "items": [
            {"name": "📱 Wymiana ekranu", "price": "od 249 zł (45 min)", "ask_detail": "Podaj model telefonu (np. iPhone 14 Pro lub Samsung S23):"},
            {"name": "🔋 Wymiana baterii", "price": "od 149 zł (30 min)", "ask_detail": "Podaj model urządzenia (np. iPhone 13 / MacBook Air M1):"},
            {"name": "🔍 Diagnostyka OBD / przegląd", "price": "100 zł (30 min)", "ask_detail": "Podaj markę, model i rocznik auta (np. Audi A4 B9 2018):"},
            {"name": "🛠 Serwis olejowy + filtry", "price": "od 120 zł (60 min)", "ask_detail": "Podaj markę, model i silnik samochodu:"},
        ],
        "quote_msg": (
            "💰 Szacunkowy koszt: <b>{price}</b>\n"
            "📌 Urządzenie / auto: <b>{detail}</b>\n\n"
            "Kliknij przycisk poniżej, aby zarezerwować cenę i wysłać zgłoszenie:"
        ),
        "share_btn": "📞 Udostępnij numer telefonu",
        "cancel_btn": "❌ Anuluj",
        "cancelled": "Wycena anulowana. Kliknij /start, aby zacząć ponownie.",
        "done_msg": (
            "✅ <b>Wycena zapisana!</b>\n\n"
            "🛠 Usługa: <b>{service}</b>\n"
            "📌 Model / auto: <b>{detail}</b>\n"
            "💰 Kwota: <b>{price}</b>\n"
            "📞 Twój kontakt: <code>{phone}</code>\n\n"
            "Doradca skontaktuje się z Tobą w ciągu 10 minut."
        ),
        "again_btn": "🔄 Oblicz inną usługę",
    },
}


def build_menu_kb(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{it['name']} ({it['price']})", callback_data=f"est:{lang}:{idx}")]
        for idx, it in enumerate(CATALOG[lang]["items"])
    ]
    switch_lang = "pl" if lang == "ua" else "ua"
    switch_label = "🇵🇱 Przełącz na Polski" if lang == "ua" else "🇺🇦 Перемкнути на Українську"
    rows.append([InlineKeyboardButton(text=switch_label, callback_data=f"menu:{switch_lang}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(CommandStart())
@router.message(Command("calc"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(EstimateStates.choosing_service)
    await message.answer(
        CATALOG["ua"]["welcome"],
        reply_markup=build_menu_kb("ua"),
    )


@router.callback_query(F.data.startswith("menu:"))
async def cb_switch_menu(callback: CallbackQuery, state: FSMContext) -> None:
    lang = callback.data.split(":", 1)[1]
    await state.clear()
    await state.set_state(EstimateStates.choosing_service)
    await callback.message.edit_text(
        CATALOG[lang]["welcome"],
        reply_markup=build_menu_kb(lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("est:"))
async def cb_select_item(callback: CallbackQuery, state: FSMContext) -> None:
    _, lang, idx_str = callback.data.split(":")
    idx = int(idx_str)
    item = CATALOG[lang]["items"][idx]

    await state.update_data(lang=lang, service=item["name"], price=item["price"])
    await state.set_state(EstimateStates.entering_device_or_car)
    await callback.message.edit_text(
        f"✅ <b>{html.escape(item['name'])}</b> — <b>{html.escape(item['price'])}</b>\n\n"
        f"{item['ask_detail']}"
    )
    await callback.answer()


@router.message(EstimateStates.entering_device_or_car, F.text)
async def msg_detail_entered(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ua")
    detail = message.text.strip()
    await state.update_data(detail=detail)
    await state.set_state(EstimateStates.sharing_contact)

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CATALOG[lang]["share_btn"], request_contact=True)],
            [KeyboardButton(text=CATALOG[lang]["cancel_btn"])],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await message.answer(
        CATALOG[lang]["quote_msg"].format(
            price=html.escape(data["price"]),
            detail=html.escape(detail),
        ),
        reply_markup=kb,
    )


@router.message(EstimateStates.sharing_contact, F.text.in_({"❌ Скасувати", "❌ Anuluj"}))
async def msg_cancel(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ua")
    await state.clear()
    await message.answer(CATALOG[lang]["cancelled"], reply_markup=ReplyKeyboardRemove())


@router.message(EstimateStates.sharing_contact, F.contact)
async def msg_contact(message: Message, state: FSMContext, bot: Bot) -> None:
    phone = message.contact.phone_number
    if not phone.startswith("+"):
        phone = f"+{phone}"
    await complete_estimate(message, state, bot, phone)


@router.message(EstimateStates.sharing_contact, F.text)
async def msg_text_phone(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = message.text.strip()
    if len("".join(c for c in raw if c.isdigit())) < 9:
        await message.answer("⚠️ Введіть коректний номер телефону або натисніть кнопку нижче.")
        return
    await complete_estimate(message, state, bot, raw)


async def complete_estimate(message: Message, state: FSMContext, bot: Bot, phone: str) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ua")
    service = data.get("service", "—")
    price = data.get("price", "—")
    detail = data.get("detail", "—")

    user = message.from_user
    username = f"@{user.username}" if user and user.username else "без username"
    full_name = html.escape(user.full_name) if user else "Клієнт"

    await message.answer(
        CATALOG[lang]["done_msg"].format(
            service=html.escape(service),
            detail=html.escape(detail),
            price=html.escape(price),
            phone=html.escape(phone),
        ),
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "👇",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=CATALOG[lang]["again_btn"], callback_data=f"menu:{lang}")]
            ]
        ),
    )

    owner_msg = (
        f"🆕 <b>НОВИЙ РОЗРАХУНОК ІЗ КАЛЬКУЛЯТОР-БОТА</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Клієнт: <b>{full_name}</b> ({html.escape(username)})\n"
        f"🛠 Послуга: <b>{html.escape(service)}</b>\n"
        f"📌 Модель / авто: <b>{html.escape(detail)}</b>\n"
        f"💰 Сума: <b>{html.escape(price)}</b>\n"
        f"📞 Телефон: <code>{html.escape(phone)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    try:
        await bot.send_message(chat_id=OWNER_CHAT_ID, text=owner_msg)
    except Exception as exc:
        logging.warning("Помилка відправки власнику: %s", exc)

    await state.clear()


async def main() -> None:
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
