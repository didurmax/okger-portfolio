"""
OK GER — портфоліо в одному процесі:
  • віддає статичний сайт із папки public/
  • приймає заявки з форм демо-сайтів на POST /api/lead і пересилає їх власнику в Telegram
  • тримає онлайн трьох демо-ботів (запис, калькулятор, бот портфоліо)

Налаштування — через змінні середовища (див. .env.example). На fly.io їх задають командою
`fly secrets set ...`, тому токени ніколи не потрапляють у код чи на сайт.
"""

import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl

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


# ==========================================================
# Telegram Mini App «Ранок»: перевірка initData і прийом замовлень
# ==========================================================

MINIAPP_DIR = PUBLIC_DIR / "miniapp"
MINIAPP_MENU = json.loads((MINIAPP_DIR / "menu.json").read_text(encoding="utf-8"))
MENU_PRODUCTS = {p["id"]: p for p in MINIAPP_MENU["products"]}
INIT_DATA_MAX_AGE = 24 * 60 * 60


def verify_init_data(init_data: str, bot_token: str) -> dict | None:
    """Перевіряє підпис initData за алгоритмом Telegram (HMAC-SHA256).
    Повертає розібрані поля, якщо дані справді прийшли з Telegram і не застаріли."""
    if not init_data or len(init_data) > 4096:
        return None
    try:
        fields = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    received_hash = fields.pop("hash", "")
    if not received_hash:
        return None
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc_hash, received_hash):
        return None
    try:
        if time.time() - int(fields.get("auth_date", "0")) > INIT_DATA_MAX_AGE:
            return None
        fields["user"] = json.loads(fields.get("user", "{}"))
    except (ValueError, TypeError):
        return None
    return fields


def price_order(items) -> tuple[list[dict], int] | None:
    """Рахує замовлення за серверним меню — ціни з клієнта не беремо на віру."""
    if not isinstance(items, list) or not 0 < len(items) <= 30:
        return None
    lines, total = [], 0
    for raw in items:
        if not isinstance(raw, dict):
            return None
        prod = MENU_PRODUCTS.get(raw.get("id"))
        qty = raw.get("qty")
        if not prod or not isinstance(qty, int) or not 1 <= qty <= 20:
            return None
        opts = raw.get("opts") if isinstance(raw.get("opts"), dict) else {}
        unit, labels = prod["price"], []
        for g in prod["groups"]:
            options = MINIAPP_MENU["groups"][g]["options"]
            chosen = next((o for o in options if o["id"] == opts.get(g)), options[0])
            unit += chosen["d"]
            if chosen["id"] not in ("none", "no", "cow", "single"):
                labels.append(chosen["label"].split(" ·")[0] if g == "size" else chosen["label"].lower())
        lines.append({"name": prod["name"], "opts": ", ".join(labels), "qty": qty, "sum": unit * qty})
        total += unit * qty
    return lines, total


async def _auto_ready(bot: Bot, user_id: int, num: str) -> None:
    await asyncio.sleep(60)
    await bot_portfolio_leads.notify_ready(bot, user_id, num)


async def handle_miniapp_order(request: web.Request) -> web.Response:
    bot: Bot | None = request.app.get("lead_bot")
    if bot is None:
        return web.json_response({"ok": False, "error": "Bot is not configured"}, status=503)
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    if not isinstance(payload, dict):
        return web.json_response({"ok": False, "error": "Invalid payload"}, status=400)

    auth = verify_init_data(str(payload.get("initData", "")), bot.token)
    user = auth.get("user") if auth else None
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
    user_id = user["id"]
    if _rate_limited(f"tg:{user_id}"):
        return web.json_response({"ok": False, "error": "Too many requests"}, status=429)

    priced = price_order(payload.get("items"))
    if not priced:
        return web.json_response({"ok": False, "error": "Invalid items"}, status=400)
    lines, total = priced
    pickup = next((o["label"] for o in MINIAPP_MENU["pickup"] if o["id"] == payload.get("pickup")), MINIAPP_MENU["pickup"][0]["label"])
    pay = next((o["label"] for o in MINIAPP_MENU["pay"] if o["id"] == payload.get("pay")), MINIAPP_MENU["pay"][0]["label"])
    comment = _clip(payload.get("comment"), 200)
    num = f"R-{secrets.randbelow(900) + 100}"
    store = MINIAPP_MENU["store"]

    items_text = "\n".join(
        f"• {html.escape(l['name'])}" + (f" ({html.escape(l['opts'])})" if l["opts"] else "") + f" × {l['qty']} — {l['sum']} zł"
        for l in lines
    )
    client_text = (
        f"☕ <b>Замовлення {num} прийнято!</b>\n\n{items_text}\n\n"
        f"<b>Разом: {total} zł</b>\n"
        f"🕒 Забрати: {html.escape(pickup.lower())} · {html.escape(store['address'])}\n"
        f"💳 Оплата: {html.escape(pay.lower())}\n\n"
        f"Напишемо сюди, щойно все буде готово."
    )
    name = _clip(" ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or "Клієнт", 80)
    uname = f"@{_clip(user['username'], 40)}" if user.get("username") else "без username"
    owner_text = (
        f"🛒 <b>НОВЕ ЗАМОВЛЕННЯ {num} — Mini App «{html.escape(store['name'])}» (демо)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 {name} ({uname})\n{items_text}\n"
        f"💰 <b>Разом: {total} zł</b>\n🕒 {html.escape(pickup)} · 💳 {html.escape(pay)}\n"
        + (f"📝 {comment}\n" if comment else "")
        + "━━━━━━━━━━━━━━━━━━"
    )

    try:
        await bot.send_message(chat_id=user_id, text=client_text)
    except Exception as exc:  # клієнт міг ще не запускати бота — замовлення все одно приймаємо
        log.warning("Mini App: не вдалося написати клієнту %s: %s", user_id, exc)
    if OWNER_CHAT_ID:
        try:
            await bot.send_message(
                chat_id=OWNER_CHAT_ID, text=owner_text, reply_markup=bot_portfolio_leads.miniapp_owner_kb(user_id, num)
            )
        except Exception as exc:
            log.warning("Mini App: не вдалося надіслати замовлення власнику: %s", exc)

    task = asyncio.create_task(_auto_ready(bot, user_id, num))
    request.app["bg_tasks"].add(task)
    task.add_done_callback(request.app["bg_tasks"].discard)
    return web.json_response({"ok": True, "order": {"num": num, "total": total}})


async def handle_miniapp_index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(MINIAPP_DIR / "index.html")


async def handle_miniapp_redirect(_: web.Request) -> web.Response:
    raise web.HTTPMovedPermanently("/miniapp/")


async def handle_health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def handle_index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(PUBLIC_DIR / "index.html")


@web.middleware
async def headers_middleware(request: web.Request, handler):
    resp = await handler(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.path.endswith((".html", "/", ".js", ".css", ".json")):
        resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


def build_web_app() -> web.Application:
    app = web.Application(middlewares=[headers_middleware], client_max_size=64 * 1024)
    app["bg_tasks"] = set()
    app.router.add_post("/api/lead", handle_lead)
    app.router.add_post("/api/miniapp/order", handle_miniapp_order)
    app.router.add_get("/miniapp", handle_miniapp_redirect)
    app.router.add_get("/miniapp/", handle_miniapp_index)
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


async def setup_miniapp_button(bot: Bot) -> None:
    """Кнопка «Mini App» біля поля вводу в боті портфоліо."""
    from aiogram.types import MenuButtonWebApp, WebAppInfo

    url = bot_portfolio_leads.miniapp_url()
    if not url:
        log.info("Mini App: адреса невідома (немає RENDER_EXTERNAL_URL / MINIAPP_URL) — кнопку не встановлено.")
        return
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Mini App", web_app=WebAppInfo(url=url)))
        log.info("Mini App: кнопку меню встановлено → %s", url)
    except Exception as exc:
        log.warning("Mini App: не вдалося встановити кнопку меню: %s", exc)


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
            await setup_miniapp_button(bot)
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
