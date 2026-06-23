import asyncio
import logging
import math
import base64
import hashlib
from ecdsa import VerifyingKey, util
from aiohttp import web, ClientSession

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN = "8840640367:AAGuUt3dCVpsMhtDTR5LTLCl8IPaqfo2f0E"  
MONO_TOKEN = "uSOf79fAIn4SsTJlGUjUt3hscfbHwnjOjbCUT-BKGdCM" # <-- Додай сюди токен Monobank
ADMIN_ID = 7066887055  

# Публічний URL твого сервера (або ngrok для тестів), куди Mono надсилатиме вебхуки
# Приклад: "https://tvoyserver.com/api/mono/webhook"
WEBHOOK_URL = "https://your-domain.com/api/mono/webhook" 

MAIN_PAGE_PHOTO_ID = "AgACAgIAAxkBAANAajZpm3Z-aR_Y62cO4aQta-JWuNUAAvMbaxsmPrFJAxIZ1PNPc2sBAAMCAAN4AAM8BA"

CHANNEL_USERNAME = "@chprrshop"
CHANNEL_URL = "https://t.me/chprrshop"
REVIEWS_URL = "https://t.me/otzivichprr"
CONDITIONS_URL = "https://t.me/ysloviyapokupki"

STARS_OPTIONS = [50, 100, 200, 250, 500, 1000]
STAR_PRICE = 0.80  # грн за 1 звезду

PREMIUM_PRICES = {
    "3": ("3 месяца", 550),
    "6": ("6 месяцев", 740),
    "12": ("1 год", 1290),
}

# Кеш для відкритого ключа Monobank
MONO_PUB_KEY_CACHE = None

# ─── STATES ───────────────────────────────────────────────────────────────────
class OrderStars(StatesGroup):
    waiting_amount = State()
    waiting_username = State()

class OrderPremium(StatesGroup):
    waiting_username = State()

# ─── MONOBANK API HELPERS ─────────────────────────────────────────────────────
async def get_mono_pub_key():
    """Отримує відкритий ключ для верифікації вебхуків та кешує його."""
    global MONO_PUB_KEY_CACHE
    if MONO_PUB_KEY_CACHE:
        return MONO_PUB_KEY_CACHE

    headers = {"X-Token": MONO_TOKEN}
    async with ClientSession() as session:
        async with session.get("https://api.monobank.ua/api/merchant/pubkey", headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                MONO_PUB_KEY_CACHE = data.get("key")
                return MONO_PUB_KEY_CACHE
    return None

def verify_signature(pub_key_base64, x_sign_base64, body_bytes):
    """Верифікує ECDSA підпис від Monobank."""
    try:
        pub_key_bytes = base64.b64decode(pub_key_base64)
        signature_bytes = base64.b64decode(x_sign_base64)
        vk = VerifyingKey.from_pem(pub_key_bytes)
        return vk.verify(signature_bytes, body_bytes, hashfunc=hashlib.sha256, sigdecode=util.sigdecode_der)
    except Exception as e:
        logging.error(f"Помилка верифікації підпису: {e}")
        return False

async def create_mono_invoice(amount_kopecks: int, reference: str, destination: str) -> str:
    """Створює рахунок в Monobank та повертає pageUrl."""
    headers = {"X-Token": MONO_TOKEN, "Content-Type": "application/json"}
    payload = {
        "amount": amount_kopecks,
        "ccy": 980,
        "merchantPaymInfo": {
            "reference": reference,
            "destination": destination
        },
        "webHookUrl": WEBHOOK_URL,
        "paymentType": "debit"
    }
    
    async with ClientSession() as session:
        async with session.post("https://api.monobank.ua/api/merchant/invoice/create", headers=headers, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("pageUrl")
            else:
                text = await resp.text()
                logging.error(f"Помилка створення рахунку Mono: {text}")
                return None

# ─── BOT HELPERS ──────────────────────────────────────────────────────────────
async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return m.status not in ("left", "kicked", "banned")
    except Exception:
        return False

def calc_stars_price(amount: int) -> int:
    return math.ceil(amount * STAR_PRICE)

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ Звёзды", callback_data="menu_stars"), InlineKeyboardButton(text="💎 Telegram Premium", callback_data="menu_premium")],
        [InlineKeyboardButton(text="💬 Отзывы", url=REVIEWS_URL), InlineKeyboardButton(text="📋 Условия покупки", url=CONDITIONS_URL)],
        [InlineKeyboardButton(text="📢 Телеграм канал", url=CHANNEL_URL)]
    ])

def sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
    ])

def stars_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for n in STARS_OPTIONS:
        price = calc_stars_price(n)
        row.append(InlineKeyboardButton(text=f"⭐️ {n} — {price} грн", callback_data=f"stars_{n}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(text="✏️ Ввести своё количество", callback_data="stars_custom")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def premium_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, (label, price) in PREMIUM_PRICES.items():
        rows.append([InlineKeyboardButton(text=f"💎 {label} — {price} грн", callback_data=f"premium_{key}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def back_kb(cb: str = "back_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data=cb)]])

async def replace_message(bot: Bot, chat_id: int, old_msg_id, text: str, reply_markup=None) -> types.Message:
    if old_msg_id:
        try: await bot.delete_message(chat_id, old_msg_id)
        except Exception: pass
    return await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="HTML")

async def send_main_page(chat_id: int, user_id: int, state: FSMContext):
    await state.clear()
    data = await state.get_data()
    old_id = data.get("last_msg_id")

    if old_id:
        try: await bot.delete_message(chat_id, old_id)
        except Exception: pass

    if await is_subscribed(bot, user_id):
        main_text = "🏪 <b>chprrshop — главное меню</b>\n\nВыберите нужный раздел:"
        try:
            sent = await bot.send_photo(chat_id, photo=MAIN_PAGE_PHOTO_ID, caption=main_text, reply_markup=main_keyboard(), parse_mode="HTML")
        except Exception:
            sent = await bot.send_message(chat_id, main_text, reply_markup=main_keyboard(), parse_mode="HTML")
    else:
        sent = await bot.send_message(chat_id, "👋 <b>Добро пожаловать в chprrshop!</b>\n\nДля использования бота необходимо подписаться на наш канал.", reply_markup=sub_keyboard(), parse_mode="HTML")
    await state.update_data(last_msg_id=sent.message_id)

# ─── BOT INITIALIZATION ───────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ─── HANDLERS ─────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(msg: types.Message, state: FSMContext):
    try: await msg.delete()
    except Exception: pass
    await send_main_page(msg.chat.id, msg.from_user.id, state)

@dp.callback_query(F.data == "check_sub")
async def check_sub(cb: types.CallbackQuery, state: FSMContext):
    if await is_subscribed(bot, cb.from_user.id):
        await cb.answer("✅ Подписка подтверждена!")
        await send_main_page(cb.message.chat.id, cb.from_user.id, state)
    else:
        await cb.answer("❌ Вы ещё не подписаны.", show_alert=True)

@dp.callback_query(F.data == "back_main")
async def back_main(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await send_main_page(cb.message.chat.id, cb.from_user.id, state)

# -- STARS --
@dp.callback_query(F.data == "menu_stars")
async def menu_stars(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sent = await replace_message(bot, cb.message.chat.id, data.get("last_msg_id"), "⭐️ <b>Покупка Telegram Stars</b>\n\nВыберите количество:", reply_markup=stars_keyboard())
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data.startswith("stars_") & ~F.data.in_({"stars_custom"}))
async def stars_pick(cb: types.CallbackQuery, state: FSMContext):
    amount = int(cb.data.split("_")[1])
    price = calc_stars_price(amount)
    await state.update_data(stars_amount=amount, stars_price=price)
    await state.set_state(OrderStars.waiting_username)
    data = await state.get_data()
    sent = await replace_message(bot, cb.message.chat.id, data.get("last_msg_id"), f"⭐️ Выбрано: <b>{amount} звёзд — {price} грн</b>\n\nВведите <b>@username</b> получателя:", reply_markup=back_kb("menu_stars"))
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data == "stars_custom")
async def stars_custom(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(OrderStars.waiting_amount)
    data = await state.get_data()
    sent = await replace_message(bot, cb.message.chat.id, data.get("last_msg_id"), "✏️ Введите <b>желаемое количество звёзд</b>:", reply_markup=back_kb("menu_stars"))
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.message(OrderStars.waiting_amount)
async def stars_custom_amount(msg: types.Message, state: FSMContext):
    try: await msg.delete()
    except Exception: pass
    if not msg.text.isdigit() or int(msg.text) < 1:
        return
    amount = int(msg.text)
    price = calc_stars_price(amount)
    await state.update_data(stars_amount=amount, stars_price=price)
    await state.set_state(OrderStars.waiting_username)
    data = await state.get_data()
    sent = await replace_message(bot, msg.chat.id, data.get("last_msg_id"), f"⭐️ Количество: <b>{amount} звёзд</b>\n💰 Стоимость: <b>{price} грн</b>\n\nВведите <b>@username</b> получателя:", reply_markup=back_kb("menu_stars"))
    await state.update_data(last_msg_id=sent.message_id)

@dp.message(OrderStars.waiting_username)
async def stars_username(msg: types.Message, state: FSMContext):
    try: await msg.delete()
    except Exception: pass
    data = await state.get_data()
    amount, price = data.get("stars_amount"), data.get("stars_price")
    recipient = msg.text.strip() if msg.text.strip().startswith('@') else f"@{msg.text.strip()}"

    # Зберігаємо дані замовлення у reference для Monobank (макс довжина дозволяє)
    reference = f"{msg.from_user.id}|stars|{amount}|{recipient}"
    destination = f"Оплата за {amount} Telegram Stars"
    
    # Автоматичне створення рахунку
    page_url = await create_mono_invoice(price * 100, reference, destination) # в копійках

    if page_url:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатити замовлення", url=page_url)],
            [InlineKeyboardButton(text="🔙 На головну", callback_data="back_main")]
        ])
        sent = await replace_message(bot, msg.chat.id, data.get("last_msg_id"), f"✅ <b>Заявка сформована!</b>\n\n⭐️ Звёзды: <b>{amount}</b>\n💰 Сумма: <b>{price} грн</b>\n👤 Получатель: <code>{recipient}</code>\n\nНатисніть кнопку нижче для безпечної оплати через Monobank.", reply_markup=markup)
    else:
        sent = await replace_message(bot, msg.chat.id, data.get("last_msg_id"), "❌ Виникла помилка при створенні рахунку. Спробуйте пізніше.", reply_markup=back_kb("menu_stars"))
    
    await state.clear()
    await state.update_data(last_msg_id=sent.message_id)


# -- PREMIUM --
@dp.callback_query(F.data == "menu_premium")
async def menu_premium(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sent = await replace_message(bot, cb.message.chat.id, data.get("last_msg_id"), "💎 <b>Telegram Premium</b>\n\nВыберите срок подписки:", reply_markup=premium_keyboard())
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data.startswith("premium_"))
async def premium_pick(cb: types.CallbackQuery, state: FSMContext):
    key = cb.data.split("_")[1]
    label, price = PREMIUM_PRICES[key]
    await state.update_data(premium_label=label, premium_price=price)
    await state.set_state(OrderPremium.waiting_username)
    data = await state.get_data()
    sent = await replace_message(bot, cb.message.chat.id, data.get("last_msg_id"), f"💎 Выбрано: <b>Telegram Premium {label} — {price} грн</b>\n\nВведите <b>@username</b> получателя:", reply_markup=back_kb("menu_premium"))
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.message(OrderPremium.waiting_username)
async def premium_username(msg: types.Message, state: FSMContext):
    try: await msg.delete()
    except Exception: pass
    data = await state.get_data()
    label, price = data.get("premium_label"), data.get("premium_price")
    recipient = msg.text.strip() if msg.text.strip().startswith('@') else f"@{msg.text.strip()}"

    reference = f"{msg.from_user.id}|premium|{label}|{recipient}"
    destination = f"Оплата за Premium ({label})"
    
    page_url = await create_mono_invoice(price * 100, reference, destination) # в копійках

    if page_url:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатити замовлення", url=page_url)],
            [InlineKeyboardButton(text="🔙 На головну", callback_data="back_main")]
        ])
        sent = await replace_message(bot, msg.chat.id, data.get("last_msg_id"), f"✅ <b>Заявка сформована!</b>\n\n💎 Premium: <b>{label}</b>\n💰 Сумма: <b>{price} грн</b>\n👤 Получатель: <code>{recipient}</code>\n\nНатисніть кнопку нижче для безпечної оплати.", reply_markup=markup)
    else:
        sent = await replace_message(bot, msg.chat.id, data.get("last_msg_id"), "❌ Виникла помилка при створенні рахунку. Спробуйте пізніше.", reply_markup=back_kb("menu_premium"))
    
    await state.clear()
    await state.update_data(last_msg_id=sent.message_id)

# ─── MONOBANK WEBHOOK HANDLER (AIOHTTP) ───────────────────────────────────────
async def handle_mono_webhook(request: web.Request):
    """Обробка сповіщень про оплату від Monobank."""
    x_sign = request.headers.get("X-Sign")
    if not x_sign:
        return web.Response(text="Missing X-Sign", status=400)

    pub_key = await get_mono_pub_key()
    if not pub_key:
        return web.Response(text="Cannot retrieve public key", status=500)

    raw_body = await request.read()
    
    if not verify_signature(pub_key, x_sign, raw_body):
        global MONO_PUB_KEY_CACHE
        MONO_PUB_KEY_CACHE = None # Скидаємо кеш, якщо підпис не зійшовся
        return web.Response(text="Invalid signature", status=400)

    data = await request.json()
    status = data.get("status")
    reference = data.get("reference")

    if status == "success" and reference:
        try:
            # Розбираємо наш reference, який ми сформували під час створення інвойсу
            user_id_str, order_type, item, recipient = reference.split("|")
            user_id = int(user_id_str)

            # 1. Повідомляємо клієнта про успішну оплату
            await bot.send_message(
                chat_id=user_id,
                text=f"🎉 <b>Оплата успішна!</b>\n\nВаше замовлення ({order_type}: {item}) для {recipient} передано в роботу. Очікуйте нарахування найближчим часом!",
                parse_mode="HTML"
            )

            # 2. Повідомляємо адміна про 100% підтверджену оплату (для видачі)
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🟢 <b>НОВА ОПЛАЧЕНА ЗАЯВКА (Monobank)</b>\n\n"
                     f"Тип: <b>{order_type.upper()}</b>\n"
                     f"Кількість/Термін: <b>{item}</b>\n"
                     f"Отримувач: <code>{recipient}</code>\n"
                     f"Сума: {data.get('amount') / 100} грн\n\n"
                     f"<i>✅ Оплата криптографічно підтверджена банком. Можна видавати товар.</i>",
                parse_mode="HTML"
            )
            # 💡 Тут можна викликати зовнішнє API для автоматичної видачі Premium/Stars, якщо воно у вас є.

        except Exception as e:
            logging.error(f"Помилка обробки успішної оплати: {e}")

    return web.Response(text="OK", status=200)

# ─── RUNNER (BOT + WEBSERVER) ─────────────────────────────────────────────────
async def main():
    # Налаштовуємо веб-сервер aiohttp
    app = web.Application()
    app.router.add_post('/api/mono/webhook', handle_mono_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    # Запускаємо веб-сервер на порту 3000
    site = web.TCPSite(runner, '0.0.0.0', 3000)
    await site.start()
    logging.info("Веб-сервер для Monobank запущено на порту 3000")

    # Запускаємо поллінг бота паралельно
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())