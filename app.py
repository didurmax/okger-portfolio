"""
OK GER — портфоліо в одному процесі:
  • віддає статичний сайт із папки public/
  • приймає заявки з форм демо-сайтів на POST /api/lead і пересилає їх власнику в Telegram
  • тримає онлайн трьох демо-ботів (запис, калькулятор, бот портфоліо)

Налаштування — через змінні середовища (див. .env.example). На fly.io їх задають командою
`fly secrets set ...`, тому токени ніколи не потрапляють у код чи на сайт.
"""

import asyncio
import html
import logging
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "bots"))

try:  # локальний запуск: підхоплюємо .env, якщо є python-dotenv
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

from aiohttp import web  # noqa: E402
from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402

import bot_booking  # noqa: E402
import bot_estimator  # noqa: E402
import bot_portfolio_leads  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("okger")

PUBLIC_DIR = BASE_DIR / "public"
PORT = int(os.getenv("PORT", os.getenv("WEB_PORT", "8080")))
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID", "0") or 0)

# Захист від спаму у формах: не більше N заявок з однієї IP за вікно часу
RATE_LIMIT = 5
RATE_WINDOW_SEC = 10 * 60
_hits: dict[str, list[float]] = {}


def _valid_token(token: str | None) -> bool:
    return bool(token) and ":" in token and not token.startswith(("YOUR_", "1234567890:AAF_"))


def _clip(value, limit: int = 300) -> str:
    return html.escape(str(value or "").strip()[:limit])


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    recent = [t for t in _hits.get(ip, []) if now - t < RATE_WINDOW_SEC]
    recent.append(now)
    _hits[ip] = recent
    return len(recent) > RATE_LIMIT


async def handle_lead(request: web.Request) -> web.Response:
    bot: Bot | None = request.app.get("lead_bot")
    if bot is None or not OWNER_CHAT_ID:
        return web.json_response({"ok": False, "error": "Lead bot is not configured"}, status=503)

    fwd = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    ip = request.headers.get("Fly-Client-IP") or fwd or request.remote or "?"
    if _rate_limited(ip):
        return web.json_response({"ok": False, "error": "Too many requests"}, status=429)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    if not isinstance(payload, dict):
        return web.json_response({"ok": False, "error": "Invalid payload"}, status=400)

    phone_raw = str(payload.get("phone", ""))
    if sum(ch.isdigit() for ch in phone_raw) < 7:
        return web.json_response({"ok": False, "error": "Invalid phone"}, status=400)

    source = _clip(payload.get("source") or "Сайт портфоліо OK GER", 120)
    service = _clip(payload.get("service") or "Не вказано")
    name = _clip(payload.get("name") or "Клієнт", 80)
    phone = _clip(phone_raw, 40)
    extra = _clip(payload.get("extra"))

    text = (
        f"🆕 <b>НОВИЙ ЛІД ІЗ САЙТУ ({source})</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 Послуга: <b>{service}</b>\n"
        f"👤 Клієнт: <b>{name}</b>\n"
        f"📞 Контакт: <code>{phone}</code>\n"
    )
    if extra:
        text += f"📝 Деталі: {extra}\n"
    text += "━━━━━━━━━━━━━━━━━━"

    try:
        await bot.send_message(
            chat_id=OWNER_CHAT_ID, text=text, reply_markup=bot_portfolio_leads.lead_status_kb()
        )
    except Exception as exc:
        log.error("Не вдалося надіслати лід у Telegram: %s", exc)
        return web.json_response({"ok": False, "error": "Telegram error"}, status=502)
    return web.json_response({"ok": True})


async def handle_health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def handle_index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(PUBLIC_DIR / "index.html")


@web.middleware
async def headers_middleware(request: web.Request, handler):
    resp = await handler(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.path.endswith(".html") or request.path == "/":
        resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


def build_web_app() -> web.Application:
    app = web.Application(middlewares=[headers_middleware], client_max_size=64 * 1024)
    app.router.add_post("/api/lead", handle_lead)
    app.router.add_get("/healthz", handle_health)
    app.router.add_get("/", handle_index)
    app.router.add_static("/", PUBLIC_DIR, show_index=False)
    return app


async def keep_awake() -> None:
    """Render (free) присипляє сервіс після 15 хв без вхідних запитів.
    Раз на 10 хв звертаємося до власної публічної адреси — запит іде через Render,
    тож сервіс (а з ним і боти) лишається активним."""
    url = os.getenv("KEEP_AWAKE_URL") or os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        return
    import aiohttp

    url = url.rstrip("/") + "/healthz"
    log.info("Keep-awake увімкнено: %s кожні 10 хв", url)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        while True:
            await asyncio.sleep(10 * 60)
            try:
                async with session.get(url) as resp:
                    log.info("Keep-awake: %s", resp.status)
            except Exception as exc:
                log.warning("Keep-awake не вдався: %s", exc)


def make_bot(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def main() -> None:
    if not OWNER_CHAT_ID:
        log.warning("OWNER_CHAT_ID не задано — заявки нікуди не прийдуть.")

    bot_booking.init_db()

    specs = [
        ("portfolio", os.getenv("PORTFOLIO_BOT_TOKEN"), bot_portfolio_leads.router),
        ("booking", os.getenv("BOOKING_BOT_TOKEN"), bot_booking.router),
        ("estimator", os.getenv("ESTIMATOR_BOT_TOKEN"), bot_estimator.router),
    ]

    app = build_web_app()
    pollers = []
    bots: list[Bot] = []
    for name, token, router in specs:
        if not _valid_token(token):
            log.warning("Бот '%s' пропущено: немає токена.", name)
            continue
        bot = make_bot(token)
        bots.append(bot)
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(router)
        if name == "portfolio":
            app["lead_bot"] = bot
        pollers.append(dp.start_polling(bot, handle_signals=False))
        log.info("Бот '%s' запускається.", name)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    log.info("Сайт працює на порту %s", PORT)
    awake_task = asyncio.create_task(keep_awake())

    try:
        if pollers:
            await asyncio.gather(*pollers)
        else:
            await asyncio.Event().wait()
    finally:
        awake_task.cancel()
        for bot in bots:
            await bot.session.close()
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
