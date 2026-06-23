import asyncio
import logging
import math
import os
import json
import asyncpg  # Змінено з aiosqlite на asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Завантажуємо .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
admin_id_raw = os.getenv("ADMIN_ID")
DATABASE_URL = os.getenv("DATABASE_URL")  # Посилання на базу даних від Railway

if not BOT_TOKEN or not admin_id_raw:
    exit("❌ Помилка: Не знайдено BOT_TOKEN або ADMIN_ID у файлі .env! Перевірте наявність файлу.")

if not DATABASE_URL:
    logging.warning("⚠️ Попередження: DATABASE_URL не знайдено. Переконайтеся, що змінна налаштована на Railway.")

ADMIN_ID = int(admin_id_raw)
MAIN_PAGE_PHOTO_ID = "AgACAgIAAxkBAANAajZpm3Z-aR_Y62cO4aQta-JWuNUAAvMbaxsmPrFJAxIZ1PNPc2sBAAMCAAN4AAM8BA"

CHANNEL_USERNAME = "@chprrshop"
CHANNEL_URL = "https://t.me/chprrshop"
REVIEWS_URL = "https://t.me/otzivichprr"
CONDITIONS_URL = "https://t.me/ysloviyapokupki"

CARD_NUMBER = "4874 0700 5861 6069"  # <-- твоя карта для оплаты

STARS_OPTIONS = [50, 100, 200, 250, 500, 1000]
STAR_PRICE = 0.80  

PREMIUM_PRICES = {
    "3": ("3 месяца", 550),
    "6": ("6 месяцев", 740),
    "12": ("1 год", 1290),
}

# ─── DATABASE (POSTGRESQL) ────────────────────────────────────────────────────

async def init_db():
    """Створює таблицю для логів у Postgres, якщо вона не існує."""
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        # У Postgres замість AUTOINCREMENT використовується SERIAL
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
        logging.info("✅ База даних PostgreSQL успішно ініціалізована.")
    except Exception as e:
        logging.error(f"❌ Помилка ініціалізації бази даних: {e}")

async def log_action(user_id: int, username: str, action: str, details: dict = None):
    """Функція для запису дії користувача в базу Postgres."""
    details_json = json.dumps(details, ensure_ascii=False) if details else ""
    uname = f"@{username}" if username else "No username"
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        # Замість знаків "?" тепер використовуються параметри "$1, $2, $3, $4"
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
    waiting_receipt = State()

class OrderPremium(StatesGroup):
    waiting_username = State()
    waiting_receipt = State()

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
        if MAIN_PAGE_PHOTO_ID and MAIN_PAGE_PHOTO_ID != "USER_PLEASE_FILL_THIS_ID":
            try:
                sent = await bot.send_photo(
                    chat_id,
                    photo=MAIN_PAGE_PHOTO_ID,
                    caption=main_text,
                    reply_markup=main_keyboard(),
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.error(f"Error sending main photo: {e}")
                sent = await bot.send_message(
                    chat_id, main_text, reply_markup=main_keyboard(), parse_mode="HTML"
                )
        else:
            sent = await bot.send_message(
                chat_id, main_text, reply_markup=main_keyboard(), parse_mode="HTML"
            )
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

# ─── BOT ──────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ─── /start ───────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(msg: types.Message, state: FSMContext):
    await log_action(msg.from_user.id, msg.from_user.username, "command_start")
    try:
        await msg.delete()
    except Exception:
        pass
    await send_main_page(msg.chat.id, msg.from_user.id, state)

# ─── CHECK SUB ────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "check_sub")
async def check_sub(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "check_subscription")
    if await is_subscribed(bot, cb.from_user.id):
        await cb.answer("✅ Подписка подтверждена!")
        await send_main_page(cb.message.chat.id, cb.from_user.id, state)
    else:
        await cb.answer("❌ Вы ещё не подписаны. Подпишитесь и попробуйте снова.", show_alert=True)

# ─── BACK MAIN ────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "back_main")
async def back_main(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "back_to_main")
    await cb.answer()
    await send_main_page(cb.message.chat.id, cb.from_user.id, state)

# ─── STARS MENU ───────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "menu_stars")
async def menu_stars(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "open_menu_stars")
    data = await state.get_data()
    old = data.get("last_msg_id")
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        "⭐️ <b>Покупка Telegram Stars</b>\n\n"
        "Выберите количество звёзд или введите своё:",
        reply_markup=stars_keyboard()
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data.startswith("stars_") & ~F.data.in_({"stars_custom"}))
async def stars_pick(cb: types.CallbackQuery, state: FSMContext):
    amount = int(cb.data.split("_")[1])
    price = calc_stars_price(amount)
    await log_action(cb.from_user.id, cb.from_user.username, "select_stars", {"amount": amount, "price": price})
    
    await state.update_data(stars_amount=amount, stars_price=price)
    await state.set_state(OrderStars.waiting_username)
    data = await state.get_data()
    old = data.get("last_msg_id")
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        f"⭐️ Выбрано: <b>{amount} звёзд — {price} грн</b>\n\n"
        "Введите <b>@username</b> или <b>числовой ID</b> аккаунта-получателя:",
        reply_markup=back_kb("menu_stars")
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data == "stars_custom")
async def stars_custom(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "select_custom_stars")
    await state.update_data(stars_amount=None, stars_price=None)
    await state.set_state(OrderStars.waiting_amount)
    data = await state.get_data()
    old = data.get("last_msg_id")
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        "✏️ Введите <b>желаемое количество звёзд</b> (например: <code>643</code>):\n\n"
        "💡 Цена рассчитывается автоматически.",
        reply_markup=back_kb("menu_stars")
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.message(OrderStars.waiting_amount)
async def stars_custom_amount(msg: types.Message, state: FSMContext):
    try:
        await msg.delete()
    except Exception:
        pass
    if not msg.text.isdigit() or int(msg.text) < 1:
        data = await state.get_data()
        old = data.get("last_msg_id")
        sent = await replace_message(
            bot, msg.chat.id, old,
            "❗️ Введите целое положительное число, например: <code>643</code>",
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
        f"⭐️ Количество: <b>{amount} звёзд</b>\n"
        f"💰 Стоимость: <b>{price} грн</b>\n\n"
        "Введите <b>@username</b> или <b>числовой ID</b> аккаунта-получателя:",
        reply_markup=back_kb("menu_stars")
    )
    await state.update_data(last_msg_id=sent.message_id)

@dp.message(OrderStars.waiting_username)
async def stars_username(msg: types.Message, state: FSMContext):
    try:
        await msg.delete()
    except Exception:
        pass
    data = await state.get_data()
    amount = data.get("stars_amount")
    price = data.get("stars_price")
    old = data.get("last_msg_id")

    input_text = msg.text.strip()
    if input_text.startswith('@'):
        recipient_display = input_text
    else:
        recipient_display = f"@{input_text}"

    await log_action(msg.from_user.id, msg.from_user.username, "order_stars_created", {
        "amount": amount, "price": price, "target_user": recipient_display
    })

    await state.update_data(order_username=recipient_display, order_type="stars")

    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Новая заявка — Звёзды</b>\n\n"
        f"👤 Покупатель: @{msg.from_user.username or msg.from_user.id} (ID: <code>{msg.from_user.id}</code>)\n"
        f"⭐️ Количество: <b>{amount}</b>\n"
        f"💰 Сумма: <b>{price} грн</b>\n"
        f"📩 Получатель: <code>{recipient_display}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить и отправить карту",
                                  callback_data=f"admin_confirm_{msg.from_user.id}")]
        ]),
        parse_mode="HTML"
    )

    await state.set_state(OrderStars.waiting_receipt)
    sent = await replace_message(
        bot, msg.chat.id, old,
        f"✅ <b>Заявка отправлена!</b>\n\n"
        f"⭐️ Звёзды: <b>{amount}</b>\n"
        f"💰 Сумма: <b>{price} грн</b>\n"
        f"👤 Получатель: <code>{recipient_display}</code>\n\n"
        "⏳ Ожидайте подтверждения от менеджера — он пришлёт реквизиты для оплаты.",
        reply_markup=back_kb("back_main")
    )
    await state.update_data(last_msg_id=sent.message_id)

# ─── PREMIUM MENU ─────────────────────────────────────────────────────────────
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
        "Введите <b>@username</b> или <b>номер телефона</b> аккаунта-получателя:",
        reply_markup=back_kb("menu_premium")
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.message(OrderPremium.waiting_username)
async def premium_username(msg: types.Message, state: FSMContext):
    try:
        await msg.delete()
    except Exception:
        pass
    data = await state.get_data()
    label = data.get("premium_label")
    price = data.get("premium_price")
    old = data.get("last_msg_id")

    input_text = msg.text.strip()
    if input_text.startswith('@'):
        recipient_display = input_text
    else:
        recipient_display = f"@{input_text}"

    await log_action(msg.from_user.id, msg.from_user.username, "order_premium_created", {
        "duration": label, "price": price, "target_user": recipient_display
    })

    await state.update_data(order_username=recipient_display, order_type="premium")

    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Новая заявка — Premium</b>\n\n"
        f"👤 Покупатель: @{msg.from_user.username or msg.from_user.id} (ID: <code>{msg.from_user.id}</code>)\n"
        f"💎 Тариф: <b>{label}</b>\n"
        f"💰 Сумма: <b>{price} грн</b>\n"
        f"📩 Получатель: <code>{recipient_display}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить и отправить карту",
                                  callback_data=f"admin_confirm_{msg.from_user.id}")]
        ]),
        parse_mode="HTML"
    )

    await state.set_state(OrderPremium.waiting_receipt)
    sent = await replace_message(
        bot, msg.chat.id, old,
        f"✅ <b>Заявка отправлена!</b>\n\n"
        f"💎 Telegram Premium: <b>{label}</b>\n"
        f"💰 Сумма: <b>{price} грн</b>\n"
        f"👤 Получатель: <code>{recipient_display}</code>\n\n"
        "⏳ Ожидайте подтверждения от менеджера — он пришлёт реквизиты для оплаты.",
        reply_markup=back_kb("back_main")
    )
    await state.update_data(last_msg_id=sent.message_id)

# ─── ADMIN CONFIRM BUTTON ─────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("admin_confirm_"))
async def admin_confirm_cb(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("У вас нет прав для этого действия.", show_alert=True)
        return

    user_id = int(cb.data.split("_")[2])
    await log_action(cb.from_user.id, cb.from_user.username, "admin_confirmed_order", {"client_id": user_id})

    await bot.send_message(
        user_id,
        f"✅ <b>Ваша заявка подтверждена!</b>\n\n"
        f"💳 Для оплаты переведите нужную сумму на карту:\n"
        f"<code>{CARD_NUMBER}</code>\n\n"
        "После оплаты нажмите <b>«Я оплатил»</b> и отправьте скриншот/чек.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я оплатил — отправить чек", callback_data="send_receipt")]
        ]),
        parse_mode="HTML"
    )

    await cb.message.edit_text(
        cb.message.html_text + "\n\n✅ <i>Реквизиты успешно отправлены! Ожидаем чек...</i>",
        reply_markup=None,
        parse_mode="HTML"
    )
    await cb.answer("Реквизиты отправлены пользователю!")

# ─── RECEIPT FLOW ─────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "send_receipt")
async def ask_receipt(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "clicked_i_paid")
    data = await state.get_data()
    old = data.get("last_msg_id")
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        "📎 <b>Отправьте чек или скриншот оплаты</b>\n\n"
        "Прикрепите фото или документ с подтверждением оплаты:",
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
    
    try:
        await msg.delete()
    except Exception:
        pass
    old = data.get("last_msg_id")

    caption = (
        f"💰 <b>Чек оплаты</b>\n"
        f"👤 Покупатель: @{msg.from_user.username or '—'} (ID: <code>{msg.from_user.id}</code>)\n"
        f"📩 Получатель: <code>{data.get('order_username', '—')}</code>"
    )
    try:
        if msg.photo:
            await bot.send_photo(ADMIN_ID, msg.photo[-1].file_id, caption=caption, parse_mode="HTML")
        elif msg.document:
            await bot.send_document(ADMIN_ID, msg.document.file_id, caption=caption, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Error forwarding receipt: {e}")

    await state.update_data(waiting_receipt=False)
    sent = await replace_message(
        bot, msg.chat.id, old,
        "🎉 <b>Чек получен!</b>\n\n"
        "Спасибо за оплату! Менеджер проверит платёж и доставит товар в ближайшее время.\n\n"
        "Если есть вопросы — обращайтесь в канал или к менеджеру.",
        reply_markup=main_keyboard()
    )
    await state.update_data(last_msg_id=sent.message_id)

# ─── RUN ──────────────────────────────────────────────────────────────────────
async def main():
    # Ініціалізація бази даних при запуску бота
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())