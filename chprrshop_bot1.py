import asyncio
import logging
import math
import os
import json
import re
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Завантажуємо .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
admin_id_raw = os.getenv("ADMIN_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN or not admin_id_raw:
    exit("❌ Помилка: Не знайдено BOT_TOKEN или ADMIN_ID у файлі .env!")

ADMIN_ID = int(admin_id_raw)

# Файл локального photo логотипу
LOCAL_PHOTO_PATH = "photo_2026-02-28_11-24-12.jpg"
cached_photo_id = None

CHANNEL_USERNAME = "@chprrshop"
CHANNEL_URL = "https://t.me/chprrshop"
REVIEWS_CHANNEL = "@otzivichprr"
REVIEWS_URL = "https://t.me/otzivichprr"
CONDITIONS_URL = "https://t.me/ysloviyapokupki"

CARD_NUMBER = "4874 0700 5861 6069"
SUPPORT_USERNAME = "@chprr"

STARS_OPTIONS = [50, 100, 200, 250, 500, 1000]
STAR_PRICE = 0.80  

PREMIUM_PRICES = {
    "3": ("3 месяца", 550),
    "6": ("6 месяцев", 740),
    "12": ("1 год", 1290),
}

# ─── DATABASE (POSTGRESQL) ────────────────────────────────────────────────────
async def init_db():
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                action TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.close()
        logging.info("✅ База даних PostgreSQL успешно инициализирована.")
    except Exception as e:
        logging.error(f"❌ Помилка ініціалізації бази даних: {e}")

async def log_action(user_id: int, username: str, action: str, details: dict = None):
    details_json = json.dumps(details, ensure_ascii=False) if details else ""
    uname = f"@{username}" if username else "No username"
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            "INSERT INTO logs (user_id, username, action, details) VALUES ($1, $2, $3, $4)",
            user_id, uname, action, details_json
        )
        await conn.close()
    except Exception as e:
        logging.error(f"❌ Помилка запису в БД: {e}")

# ─── STATES ───────────────────────────────────────────────────────────────────
class OrderStars(StatesGroup):
    waiting_amount = State()
    waiting_username = State()
    waiting_confirmation = State()
    waiting_receipt = State()

class OrderPremium(StatesGroup):
    waiting_username = State()
    waiting_confirmation = State()
    waiting_receipt = State()

class AdminWorkflow(StatesGroup):
    waiting_decline_reason = State()

class UserFeedback(StatesGroup):
    waiting_review = State()

# ─── HELPERS ──────────────────────────────────────────────────────────────────
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
        [
            InlineKeyboardButton(text="⭐️ Звёзды", callback_data="menu_stars"),
            InlineKeyboardButton(text="💎 Telegram Premium", callback_data="menu_premium"),
        ],
        [
            InlineKeyboardButton(text="💬 Отзывы", url=REVIEWS_URL),
            InlineKeyboardButton(text="📋 Условия покупки", url=CONDITIONS_URL),
        ],
        [
            InlineKeyboardButton(text="📢 Телеграм канал", url=CHANNEL_URL),
        ],
    ])

def sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")],
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
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✏️ Ввести своё количество", callback_data="stars_custom")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def premium_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, (label, price) in PREMIUM_PRICES.items():
        rows.append([InlineKeyboardButton(
            text=f"💎 {label} — {price} грн",
            callback_data=f"premium_{key}"
        )])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def back_kb(cb: str = "back_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=cb)]
    ])

# ─── SAFE EDIT / DELETE + SEND ────────────────────────────────────────────────
async def replace_message(
        bot: Bot,
        chat_id: int,
        old_msg_id,
        text: str,
        reply_markup=None,
        parse_mode: str = "HTML"
) -> types.Message:
    if old_msg_id:
        try:
            await bot.delete_message(chat_id, old_msg_id)
        except Exception:
            pass
    return await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)

async def send_main_page(chat_id: int, user_id: int, state: FSMContext):
    global cached_photo_id
    await state.clear()
    data = await state.get_data()
    old_id = data.get("last_msg_id")

    if old_id:
        try:
            await bot.delete_message(chat_id, old_id)
        except Exception:
            pass

    if await is_subscribed(bot, user_id):
        main_text = "🏪 <b>chprrshop — главное меню</b>\n\nВыберите нужный раздел:"
        
        if cached_photo_id:
            try:
                sent = await bot.send_photo(chat_id, photo=cached_photo_id, caption=main_text, reply_markup=main_keyboard(), parse_mode="HTML")
            except Exception:
                cached_photo_id = None

        if not cached_photo_id:
            if os.path.exists(LOCAL_PHOTO_PATH):
                try:
                    photo_file = FSInputFile(LOCAL_PHOTO_PATH)
                    sent = await bot.send_photo(chat_id, photo=photo_file, caption=main_text, reply_markup=main_keyboard(), parse_mode="HTML")
                    if sent.photo:
                        cached_photo_id = sent.photo[-1].file_id
                except Exception as e:
                    logging.error(f"Error sending local photo: {e}")
                    sent = await bot.send_message(chat_id, main_text, reply_markup=main_keyboard(), parse_mode="HTML")
            else:
                logging.warning(f"⚠️ Файл {LOCAL_PHOTO_PATH} не найден на сервере Railway!")
                sent = await bot.send_message(chat_id, main_text, reply_markup=main_keyboard(), parse_mode="HTML")
    else:
        sent = await bot.send_message(
            chat_id,
            "👋 <b>Добро пожаловать в chprrshop!</b>\n\n"
            "Для использования бота необходимо подписаться на наш канал.\n"
            "Там вы найдёте актуальные предложения, акции и новинки.\n\n"
            "⬇️ Нажмите <b>«Подписаться»</b>, а затем <b>«Я подписался»</b>.",
            reply_markup=sub_keyboard(),
            parse_mode="HTML"
        )
    await state.update_data(last_msg_id=sent.message_id)

# ─── BOT INITIALIZATION ───────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ─── /start ───────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(msg: types.Message, state: FSMContext):
    await log_action(msg.from_user.id, msg.from_user.username, "command_start")
    await send_main_page(msg.chat.id, msg.from_user.id, state)

# ─── CHECK SUB / BACK MAIN ────────────────────────────────────────────────────
@dp.callback_query(F.data == "check_sub")
async def check_sub(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "check_subscription")
    if await is_subscribed(bot, cb.from_user.id):
        await cb.answer("✅ Подписка подтверждена!")
        await send_main_page(cb.message.chat.id, cb.from_user.id, state)
    else:
        await cb.answer("❌ Вы ещё не подписаны. Подпишитесь и попробуйте снова.", show_alert=True)

@dp.callback_query(F.data == "back_main")
async def back_main(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "back_to_main")
    await cb.answer()
    await send_main_page(cb.message.chat.id, cb.from_user.id, state)

# ─── DYNAMIC BACK FROM USERNAME ───────────────────────────────────────────────
@dp.callback_query(F.data == "back_from_username_stars")
async def back_from_username_stars(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    is_custom = data.get("is_custom", False)
    old = data.get("last_msg_id")
    
    if is_custom:
        await state.set_state(OrderStars.waiting_amount)
        sent = await replace_message(
            bot, cb.message.chat.id, old,
            "✏️ Введите желаемое количество звёзд (минимально: 50):\n\n💡 Цена рассчитывается автоматически.",
            reply_markup=back_kb("menu_stars")
        )
        await state.update_data(last_msg_id=sent.message_id)
    else:
        await menu_stars(cb, state)
    await cb.answer()

# ─── STARS FLOW ───────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "menu_stars")
async def menu_stars(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "open_menu_stars")
    data = await state.get_data()
    old = data.get("last_msg_id")
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        "⭐️ <b>Покупка Telegram Stars</b>\n\nВыберите количество звёзд или введите своё:",
        reply_markup=stars_keyboard()
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data.startswith("stars_") & ~F.data.in_({"stars_custom"}))
async def stars_pick(cb: types.CallbackQuery, state: FSMContext):
    amount = int(cb.data.split("_")[1])
    price = calc_stars_price(amount)
    await log_action(cb.from_user.id, cb.from_user.username, "select_stars", {"amount": amount, "price": price})
    
    await state.update_data(stars_amount=amount, stars_price=price, is_custom=False)
    await state.set_state(OrderStars.waiting_username)
    data = await state.get_data()
    old = data.get("last_msg_id")
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        f"⭐️ Выбрано: <b>{amount} звёзд — {price} грн</b>\n\n"
        "Введите username получателя:",
        reply_markup=back_kb("back_from_username_stars")
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data == "stars_custom")
async def stars_custom(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "select_custom_stars")
    await state.set_state(OrderStars.waiting_amount)
    await state.update_data(is_custom=True)
    data = await state.get_data()
    old = data.get("last_msg_id")
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        "✏️ Введите желаемое количество звёзд (минимально: 50):\n\n💡 Цена рассчитывается автоматически.",
        reply_markup=back_kb("menu_stars")
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.message(OrderStars.waiting_amount)
async def stars_custom_amount(msg: types.Message, state: FSMContext):
    try: await msg.delete()
    except Exception: pass
    
    if not msg.text.isdigit() or int(msg.text) < 50:
        data = await state.get_data()
        old = data.get("last_msg_id")
        sent = await replace_message(
            bot, msg.chat.id, old,
            "❗️ Минимальное количество звёзд для заказа — <b>50</b>. Введите корректное число:",
            reply_markup=back_kb("menu_stars")
        )
        await state.update_data(last_msg_id=sent.message_id)
        return
        
    amount = int(msg.text)
    price = calc_stars_price(amount)
    await log_action(msg.from_user.id, msg.from_user.username, "input_custom_stars", {"amount": amount, "price": price})
    
    await state.update_data(stars_amount=amount, stars_price=price)
    await state.set_state(OrderStars.waiting_username)
    data = await state.get_data()
    old = data.get("last_msg_id")
    sent = await replace_message(
        bot, msg.chat.id, old,
        f"⭐️ Количество: <b>{amount} звёзд</b>\n💰 Стоимость: <b>{price} грн</b>\n\n"
        "Введите username получателя:",
        reply_markup=back_kb("back_from_username_stars")
    )
    await state.update_data(last_msg_id=sent.message_id)

@dp.message(OrderStars.waiting_username)
async def stars_username(msg: types.Message, state: FSMContext):
    try: await msg.delete()
    except Exception: pass
    
    data = await state.get_data()
    amount = data.get("stars_amount")
    price = data.get("stars_price")
    old = data.get("last_msg_id")
    
    input_text = msg.text.strip().replace('@', '')
    if not re.match(r'^[a-zA-Z0-9_]+$', input_text):
        sent = await replace_message(
            bot, msg.chat.id, old,
            f"❗️ <b>Ошибка: Имя должно быть только на английском языке!</b>\n\n"
            f"⭐️ Выбрано: <b>{amount} звёзд — {price} грн</b>\n\n"
            f"Введите корректный username получателя:",
            reply_markup=back_kb("back_from_username_stars")
        )
        await state.update_data(last_msg_id=sent.message_id)
        return

    recipient_display = f"@{input_text}"
    await state.update_data(order_username=recipient_display, order_type="stars", client_id=msg.from_user.id, client_name=msg.from_user.username)
    await state.set_state(OrderStars.waiting_confirmation)

    verify_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Все верно, заказать", callback_data="user_confirm_stars")],
        [InlineKeyboardButton(text="🔙 Изменить юзернейм", callback_data="user_back_stars_username")]
    ])

    sent = await replace_message(
        bot, msg.chat.id, old,
        f"📋 <b>Проверка данных заказа</b>\n\n"
        f"⭐️ Товар: <b>{amount} Звёзд</b>\n"
        f"💰 Сумма к оплате: <b>{price} грн</b>\n"
        f"📩 Получатель: <code>{recipient_display}</code>\n\n"
        f"Проверьте правильность данных и нажмите кнопку подтверждения:",
        reply_markup=verify_markup
    )
    await state.update_data(last_msg_id=sent.message_id)

@dp.callback_query(F.data == "user_back_stars_username")
async def user_back_stars_username(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(OrderStars.waiting_username)
    data = await state.get_data()
    amount = data.get("stars_amount")
    price = data.get("stars_price")
    old = data.get("last_msg_id")
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        f"⭐️ Количество: <b>{amount} звёзд</b>\n💰 Стоимость: <b>{price} грн</b>\n\n"
        "Введите username получателя:",
        reply_markup=back_kb("back_from_username_stars")
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data == "user_confirm_stars")
async def user_confirm_stars(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = data.get("stars_amount")
    price = data.get("stars_price")
    recipient_display = data.get("order_username")
    client_id = data.get("client_id")
    client_name = data.get("client_name")
    old = data.get("last_msg_id")

    await log_action(client_id, client_name, "order_stars_created", {
        "amount": amount, "price": price, "target_user": recipient_display
    })

    # Добавляем цену в callback_data кнопки подтверждения для админа
    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить и отправить карту", callback_data=f"admin_confirm_{client_id}_{price}")],
        [InlineKeyboardButton(text="❌ Отклонить заказ", callback_data=f"admin_predecline_{client_id}")]
    ])

    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Новая заявка — Звёзды</b>\n\n"
        f"👤 Покупатель: @{client_name or client_id} (ID: <code>{client_id}</code>)\n"
        f"⭐️ Количество: <b>{amount}</b>\n"
        f"💰 Сумма: <b>{price} грн</b>\n"
        f"📩 Получатель: <code>{recipient_display}</code>",
        reply_markup=admin_markup,
        parse_mode="HTML"
    )

    await state.set_state(OrderStars.waiting_receipt)
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        f"✅ <b>Заявка отправлена!</b>\n\n⭐️ Звёзды: <b>{amount}</b>\n💰 Сумма: <b>{price} грн</b>\n👤 Получатель: <code>{recipient_display}</code>\n\n"
        "⏳ Ожидайте подтверждения от менеджера — он пришлёт реквизиты для оплаты.",
        reply_markup=back_kb("back_main")
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

# ─── PREMIUM FLOW ─────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "menu_premium")
async def menu_premium(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "open_menu_premium")
    data = await state.get_data()
    old = data.get("last_msg_id")
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        "💎 <b>Telegram Premium</b>\n\nВыберите срок подписки:",
        reply_markup=premium_keyboard()
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data.startswith("premium_"))
async def premium_pick(cb: types.CallbackQuery, state: FSMContext):
    key = cb.data.split("_")[1]
    label, price = PREMIUM_PRICES[key]
    await log_action(cb.from_user.id, cb.from_user.username, "select_premium", {"duration": label, "price": price})
    
    await state.update_data(premium_label=label, premium_price=price)
    await state.set_state(OrderPremium.waiting_username)
    data = await state.get_data()
    old = data.get("last_msg_id")
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        f"💎 Выбрано: <b>Telegram Premium {label} — {price} грн</b>\n\n"
        "Введите username получателя:",
        reply_markup=back_kb("menu_premium")
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.message(OrderPremium.waiting_username)
async def premium_username(msg: types.Message, state: FSMContext):
    try: await msg.delete()
    except Exception: pass
    
    data = await state.get_data()
    label = data.get("premium_label")
    price = data.get("premium_price")
    old = data.get("last_msg_id")

    input_text = msg.text.strip().replace('@', '')
    if not re.match(r'^[a-zA-Z0-9_]+$', input_text):
        sent = await replace_message(
            bot, msg.chat.id, old,
            f"❗️ <b>Ошибка: Имя должно быть только на английском языке!</b>\n\n"
            f"💎 Выбрано: <b>Telegram Premium {label} — {price} грн</b>\n\n"
            f"Введите корректный username получателя:",
            reply_markup=back_kb("menu_premium")
        )
        await state.update_data(last_msg_id=sent.message_id)
        return

    recipient_display = f"@{input_text}"
    await state.update_data(order_username=recipient_display, order_type="premium", client_id=msg.from_user.id, client_name=msg.from_user.username)
    await state.set_state(OrderPremium.waiting_confirmation)

    verify_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Все верно, заказать", callback_data="user_confirm_premium")],
        [InlineKeyboardButton(text="🔙 Изменить юзернейм", callback_data="user_back_premium_username")]
    ])

    sent = await replace_message(
        bot, msg.chat.id, old,
        f"📋 <b>Проверка данных заказа</b>\n\n"
        f"💎 Товар: <b>Telegram Premium {label}</b>\n"
        f"💰 Сумма к оплате: <b>{price} грн</b>\n"
        f"📩 Получатель: <code>{recipient_display}</code>\n\n"
        f"Проверьте правильность данных и нажмите кнопку подтверждения:",
        reply_markup=verify_markup
    )
    await state.update_data(last_msg_id=sent.message_id)

@dp.callback_query(F.data == "user_back_premium_username")
async def user_back_premium_username(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(OrderPremium.waiting_username)
    data = await state.get_data()
    label = data.get("premium_label")
    price = data.get("premium_price")
    old = data.get("last_msg_id")
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        f"💎 Выбрано: <b>Telegram Premium {label} — {price} грн</b>\n\n"
        "Введите username получателя:",
        reply_markup=back_kb("menu_premium")
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data == "user_confirm_premium")
async def user_confirm_premium(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    label = data.get("premium_label")
    price = data.get("premium_price")
    recipient_display = data.get("order_username")
    client_id = data.get("client_id")
    client_name = data.get("client_name")
    old = data.get("last_msg_id")

    await log_action(client_id, client_name, "order_premium_created", {
        "duration": label, "price": price, "target_user": recipient_display
    })

    # Добавляем цену в callback_data кнопки подтверждения для админа
    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить и отправить карту", callback_data=f"admin_confirm_{client_id}_{price}")],
        [InlineKeyboardButton(text="❌ Отклонить заказ", callback_data=f"admin_predecline_{client_id}")]
    ])

    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Новая заявка — Premium</b>\n\n"
        f"👤 Покупатель: @{client_name or client_id} (ID: <code>{client_id}</code>)\n"
        f"💎 Тариф: <b>{label}</b>\n"
        f"💰 Сумма: <b>{price} грн</b>\n"
        f"📩 Получатель: <code>{recipient_display}</code>",
        reply_markup=admin_markup,
        parse_mode="HTML"
    )

    await state.set_state(OrderPremium.waiting_receipt)
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        f"✅ <b>Заявка отправлена!</b>\n\n💎 Telegram Premium: <b>{label}</b>\n💰 Сумма: <b>{price} грн</b>\n👤 Получатель: <code>{recipient_display}</code>\n\n"
        "⏳ Ожидайте подтверждения от менеджера — он пришлёт реквизиты для оплаты.",
        reply_markup=back_kb("back_main")
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

# ─── ADMIN FLOW (CONFIRM, DECLINE, COMPLETE) ─────────────────────────────────
@dp.callback_query(F.data.startswith("admin_confirm_"))
async def admin_confirm_cb(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    
    # Извлекаем id пользователя и сумму из callback_data
    parts = cb.data.split("_")
    user_id = int(parts[2])
    price = parts[3] if len(parts) > 3 else "нужную"
    
    await log_action(cb.from_user.id, cb.from_user.username, "admin_confirmed_order", {"client_id": user_id, "price": price})

    # Отправляем сообщение клиенту с динамической суммой к оплате
    await bot.send_message(
        user_id,
        f"✅ <b>Ваша заявка подтверждена!</b>\n\n"
        f"💳 Для оплаты переведите ровно <b>{price} грн</b> на карту:\n"
        f"<code>{CARD_NUMBER}</code>\n\n"
        "После оплаты нажмите <b>«Я оплатил»</b> и отправьте скриншот/чек.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я оплатил — отправить чек", callback_data="send_receipt")]
        ]),
        parse_mode="HTML"
    )
    await cb.message.edit_text(cb.message.html_text + f"\n\n✅ <i>Реквизиты на сумму {price} грн отправлены пользователю! Ожидаем чек...</i>", reply_markup=None, parse_mode="HTML")
    await cb.answer()

# Двойное подтверждение отклонения
@dp.callback_query(F.data.startswith("admin_predecline_"))
async def admin_predecline(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    user_id = int(cb.data.split("_")[2])
    
    base_text = cb.message.html_text.split("\n\n⚠️")[0]
    
    confirm_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💥 Да, точно отклонить", callback_data=f"admin_decline_confirm_{user_id}")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"admin_decline_cancel_{user_id}")]
    ])
    await cb.message.edit_text(base_text + "\n\n⚠️ <b>Вы уверены, что хотите отклонить заказ?</b>", reply_markup=confirm_markup, parse_mode="HTML")
    await cb.answer()

# Скасування відхилення
@dp.callback_query(F.data.startswith("admin_decline_cancel_"))
async def admin_decline_cancel(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    
    # Пытаемся извлечь цену из текста или истории, если не получится — админу просто вернутся базовые кнопки
    user_id = int(cb.data.split("_")[3])
    base_text = cb.message.html_text.split("\n\n⚠️")[0]
    
    # Ищем сумму в тексте админ-сообщения
    price_match = re.search(r"Сумма:\s*(\d+)", base_text)
    price = price_match.group(1) if price_match else "нужную"
    
    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить и отправить карту", callback_data=f"admin_confirm_{user_id}_{price}")],
        [InlineKeyboardButton(text="❌ Отклонить заказ", callback_data=f"admin_predecline_{user_id}")]
    ])
    await cb.message.edit_text(base_text, reply_markup=admin_markup, parse_mode="HTML")
    await cb.answer()

@dp.callback_query(F.data.startswith("admin_decline_confirm_"))
async def admin_decline_confirm(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID: return
    user_id = int(cb.data.split("_")[3])
    
    base_text = cb.message.html_text.split("\n\n⚠️")[0]
    await state.set_state(AdminWorkflow.waiting_decline_reason)
    await state.update_data(decline_target_user=user_id, admin_msg_to_edit=cb.message.message_id, admin_text_history=base_text)
    await cb.message.reply("📝 Введите <b>причину отказа</b> для клиента:", parse_mode="HTML")
    await cb.answer()

@dp.message(AdminWorkflow.waiting_decline_reason)
async def admin_input_reason(msg: types.Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    reason = msg.text.strip()
    data = await state.get_data()
    user_id = data.get("decline_target_user")
    old_msg_id = data.get("admin_msg_to_edit")
    old_text = data.get("admin_text_history")
    
    await log_action(ADMIN_ID, msg.from_user.username, "admin_declined_order", {"client_id": user_id, "reason": reason})

    # Оповещаем клиента
    await bot.send_message(
        user_id,
        f"❌ <b>Ваш заказ отклонен менеджером</b>\n\n"
        f"📝 Причина: <code>{reason}</code>\n\n"
        f"📞 Обратная связь: {SUPPORT_USERNAME}",
        parse_mode="HTML"
    )
    
    # Обновляем сообщение у админа
    try:
        await bot.edit_message_text(
            chat_id=ADMIN_ID,
            message_id=old_msg_id,
            text=old_text + f"\n\n❌ <b>Заказ отклонён. Причина:</b> {reason}",
            parse_mode="HTML"
        )
    except Exception:
        pass
        
    await state.clear()
    await msg.reply("✅ <b>Клиент успешно уведомлен об отказе.</b>", parse_mode="HTML")

@dp.callback_query(F.data.startswith("admin_complete_"))
async def admin_complete_order(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    user_id = int(cb.data.split("_")[2])
    
    await log_action(ADMIN_ID, cb.from_user.username, "admin_completed_order", {"client_id": user_id})

    # Отправляем сообщение клиенту с кнопкой отзыва
    await bot.send_message(
        user_id,
        "🎉 <b>Ваш заказ успешно выполнен!</b>\n\nСпасибо, что выбрали нас. Пожалуйста, оставьте отзыв о нашей работе, нажав на кнопку ниже:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Оставить отзыв", callback_data="user_leave_review")]
        ]),
        parse_mode="HTML"
    )

    await cb.message.edit_text(cb.message.html_text + "\n\n🚀 <b>Заказ выполнен! Клиенту отправлено уведомление.</b>", reply_markup=None, parse_mode="HTML")
    await cb.answer("Заказ помечен как выполненный!")

# ─── RECEIPT & REVIEW FLOW ────────────────────────────────────────────────────
@dp.callback_query(F.data == "send_receipt")
async def ask_receipt(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "clicked_i_paid")
    data = await state.get_data()
    old = data.get("last_msg_id")
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        "📎 <b>Отправьте чек или скриншот оплаты</b>\n\nПрикрепите фото или document с подтверждением оплаты:",
        reply_markup=back_kb("back_main")
    )
    await state.update_data(last_msg_id=sent.message_id, waiting_receipt=True)
    await cb.answer()

@dp.message(F.photo | F.document)
async def receive_receipt(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("waiting_receipt"):
        return
        
    await log_action(msg.from_user.id, msg.from_user.username, "sent_receipt", {"order_type": data.get("order_type")})
    try: await msg.delete()
    except Exception: pass
    old = data.get("last_msg_id")

    client_id = data.get("client_id", msg.from_user.id)
    caption = (
        f"💰 <b>Чек оплаты получен!</b>\n"
        f"👤 Покупатель: @{msg.from_user.username or '—'} (ID: <code>{client_id}</code>)\n"
        f"📩 Получатель: <code>{data.get('order_username', '—')}</code>"
    )
    
    complete_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Заказ выполнен", callback_data=f"admin_complete_{client_id}")]
    ])

    try:
        if msg.photo:
            await bot.send_photo(ADMIN_ID, msg.photo[-1].file_id, caption=caption, reply_markup=complete_markup, parse_mode="HTML")
        elif msg.document:
            await bot.send_document(ADMIN_ID, msg.document.file_id, caption=caption, reply_markup=complete_markup, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Error forwarding receipt: {e}")

    await state.set_state(None)
    await state.update_data(waiting_receipt=False)
    sent = await replace_message(
        bot, msg.chat.id, old,
        "🎉 <b>Чек получен!</b>\n\nМенеджер проверит платёж и доставит товар в ближайшее время.",
        reply_markup=main_keyboard()
    )
    await state.update_data(last_msg_id=sent.message_id)

# Обработка отзыва
@dp.callback_query(F.data == "user_leave_review")
async def user_pre_review(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserFeedback.waiting_review)
    sent = await bot.send_message(cb.message.chat.id, "📝 Напишите ваш отзыв в одном сообщении, и он автоматически опубликуется в нашем канале:", parse_mode="HTML")
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.message(UserFeedback.waiting_review)
async def user_input_review(msg: types.Message, state: FSMContext):
    review_text = msg.text.strip()
    user_name = f"@{msg.from_user.username}" if msg.from_user.username else "Клиент"
    
    await log_action(msg.from_user.id, msg.from_user.username, "left_review")

    # Публикация отзыва в канал
    try:
        await bot.send_message(
            chat_id=REVIEWS_CHANNEL,
            text=f"💬 <b>Новый отзыв от {user_name}:</b>\n\n«{review_text}»\n\n🏪 @chprrshop",
            parse_mode="HTML"
        )
        await msg.reply("❤️ <b>Спасибо за ваш отзыв!</b> Он успешно опубликован в канале отзывов.", parse_mode="HTML")
    except Exception as e:
        logging.error(f"Error publishing review: {e}")
        await msg.reply("❌ Не удалось отправить отзыв в канал. Связывайтесь с администрацией.", parse_mode="HTML")

    await state.clear()
    await send_main_page(msg.chat.id, msg.from_user.id, state)

# ─── RUN ──────────────────────────────────────────────────────────────────────
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())