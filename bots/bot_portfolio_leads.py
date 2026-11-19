import asyncio
import html
import logging
import os
from datetime import datetime

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# ==========================================================
# OK GER Portfolio Bot + Website Lead Bridge (aiohttp + aiogram)
# Приймає заявки як напряму в Telegram, так і з HTML-форм портфоліо
# (lead-form-demo.html, landing-demo.html, info-site-demo.html)
# ==========================================================

BOT_TOKEN = os.getenv("PORTFOLIO_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID", "123456789"))
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
API_SECRET = os.getenv("API_SECRET", "okger-secret-key")

logging.basicConfig(level=logging.INFO)
router = Router()


class OrderStates(StatesGroup):
    entering_contact = State()


PACKAGES = {
    "landing": "🌐 Лендінг / Сайт-візитівка (600 zł)",
    "company": "🏢 Сайт компанії під ключ (від 850 zł)",
    "bot": "🤖 Telegram-бот для автозапису (від 500 zł)",
    "combo": "🚀 Сайт + Telegram-бот під ключ (від 1150 zł)",
}


def portfolio_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=PACKAGES["landing"], callback_data="pkg:landing")],
            [InlineKeyboardButton(text=PACKAGES["company"], callback_data="pkg:company")],
            [InlineKeyboardButton(text=PACKAGES["bot"], callback_data="pkg:bot")],
            [InlineKeyboardButton(text=PACKAGES["combo"], callback_data="pkg:combo")],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👋 <b>OK GER — Розробка сайтів та Telegram-ботів у Варшаві</b>\n\n"
        "Оберіть рішення, яке вас цікавить, щоб отримати точний прорахунок та терміни запуску:",
        reply_markup=portfolio_kb(),
    )


@router.callback_query(F.data.startswith("pkg:"))
async def cb_pick_package(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":", 1)[1]
    pkg_name = PACKAGES.get(key, PACKAGES["landing"])
    await state.update_data(package=pkg_name)
    await state.set_state(OrderStates.entering_contact)
    await callback.message.edit_text(
        f"✅ Обрано: <b>{html.escape(pkg_name)}</b>\n\n"
        "Напишіть ваш <b>номер телефону</b> або <b>@Telegram</b> та коротко вкажіть нішу бізнесу:"
    )
    await callback.answer()


@router.message(OrderStates.entering_contact, F.text)
async def msg_client_order(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    pkg_name = data.get("package", "Не вказано")
    details = message.text.strip()
    user = message.from_user
    username = f"@{user.username}" if user and user.username else "без username"
    full_name = html.escape(user.full_name) if user else "Клієнт"

    await message.answer(
        "✅ <b>Заявку передано!</b>\n\n"
        f"📌 Пакет: <b>{html.escape(pkg_name)}</b>\n"
        f"📝 Деталі: {html.escape(details)}\n\n"
        "Зв'яжемося з вами найближчим часом."
    )

    lead_card = (
        f"🔥 <b>НОВА ЗАЯВКА З БОТА ПОРТФОЛІО OK GER</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Клієнт: <b>{full_name}</b> ({html.escape(username)})\n"
        f"📌 Пакет: <b>{html.escape(pkg_name)}</b>\n"
        f"📞 Контакт / ніша: <code>{html.escape(details)}</code>\n"
        f"🕒 Час: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    try:
        await bot.send_message(chat_id=OWNER_CHAT_ID, text=lead_card, reply_markup=lead_status_kb())
    except Exception as exc:
        logging.warning("Помилка відправки власнику: %s", exc)

    await state.clear()


def lead_status_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📞 Взято в роботу", callback_data="lead_st:work"),
                InlineKeyboardButton(text="✅ Угода закрита", callback_data="lead_st:done"),
            ]
        ]
    )


@router.callback_query(F.data.startswith("lead_st:"))
async def cb_lead_status(callback: CallbackQuery) -> None:
    st = callback.data.split(":", 1)[1]
    label = "\n\n🟡 <b>Статус: Взято в роботу</b>" if st == "work" else "\n\n🟢 <b>Статус: Угода закрита</b>"
    await callback.message.edit_text(callback.message.html_text + label)
    await callback.answer("Оновлено")


# ==========================================================
# HTTP API Endpoint для прийому заявок з HTML-сайтів портфоліо
# ==========================================================

@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Api-Key"
    return resp


async def handle_web_lead(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    if API_SECRET and request.headers.get("X-Api-Key") not in (API_SECRET, None):
        return web.json_response({"ok": False, "error": "Invalid API key"}, status=403)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    source = html.escape(str(payload.get("source", "Сайт портфоліо OK GER")))
    service = html.escape(str(payload.get("service", "Не вказано")))
    name = html.escape(str(payload.get("name", "Клієнт")))
    phone = html.escape(str(payload.get("phone", "—")))
    extra = html.escape(str(payload.get("extra", "")))

    text = (
        f"🆕 <b>НОВИЙ ЛІД ІЗ САЙТУ ({source})</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 Послуга: <b>{service}</b>\n"
        f"👤 Клієнт: <b>{name}</b>\n"
        f"📞 Контакт: <code>{phone}</code>\n"
    )
    if extra:
        text += f"🚗 Деталі: {extra}\n"
    text += "━━━━━━━━━━━━━━━━━━"

    try:
        await bot.send_message(chat_id=OWNER_CHAT_ID, text=text, reply_markup=lead_status_kb())
        return web.json_response({"ok": True})
    except Exception as exc:
        logging.error("Помилка Telegram API: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def main() -> None:
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    app = web.Application(middlewares=[cors_middleware])
    app["bot"] = bot
    app.router.add_post("/api/lead", handle_web_lead)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_HOST, WEB_PORT)
    await site.start()
    logging.info("HTTP API запущено на http://%s:%s/api/lead", WEB_HOST, WEB_PORT)

    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
