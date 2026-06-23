import asyncio
import logging
import math
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN   = "8840640367:AAGuUt3dCVpsMhtDTR5LTLCl8IPaqfo2f0E"   # <-- токен от @BotFather
ADMIN_ID    = 7066887055               # <-- твой Telegram ID (число)

CHANNEL_USERNAME = "@chprrshop"
CHANNEL_URL      = "https://t.me/chprrshop"
REVIEWS_URL      = "https://t.me/otzivichprr"
CONDITIONS_URL   = "https://t.me/ysloviyapokupki"

CARD_NUMBER = "4874 0700 5861 6069"   # <-- твоя карта для оплаты

STARS_OPTIONS = [50, 100, 200, 250, 500, 1000]
# Цена: 50 зв = 40 грн  →  1 звезда = 0.80 грн
STAR_PRICE = 0.80  # грн за 1 звезду (50*0.80=40, 100*0.80=80)

PREMIUM_PRICES = {
    "3":  ("3 месяца",  550),
    "6":  ("6 месяцев", 740),
    "12": ("1 год",    1290),
}

# ─── STATES ───────────────────────────────────────────────────────────────────
class OrderStars(StatesGroup):
    waiting_amount   = State()
    waiting_username = State()
    waiting_receipt  = State()

class OrderPremium(StatesGroup):
    waiting_username = State()
    waiting_receipt  = State()

class AdminConfirm(StatesGroup):
    pass

# ─── HELPERS ──────────────────────────────────────────────────────────────────
async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return m.status not in ("left", "kicked", "banned")
    except Exception:
        return False

def calc_stars_price(amount: int) -> int:
    """50 зв = 40 грн, 100 = 80. Для произвольного: amount * 0.80, округление вверх."""
    return math.ceil(amount * STAR_PRICE)

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📢 Телеграм канал",  url=CHANNEL_URL),
            InlineKeyboardButton(text="💬 Отзывы",          url=REVIEWS_URL),
        ],
        [
            InlineKeyboardButton(text="📋 Условия покупки", url=CONDITIONS_URL),
        ],
        [
            InlineKeyboardButton(text="⭐️ Звёзды",          callback_data="menu_stars"),
            InlineKeyboardButton(text="💎 Telegram Premium", callback_data="menu_premium"),
        ],
    ])

def sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Я подписался",          callback_data="check_sub")],
    ])

def stars_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row  = []
    for n in STARS_OPTIONS:
        price = calc_stars_price(n)
        row.append(InlineKeyboardButton(text=f"⭐️ {n} — {price} грн", callback_data=f"stars_{n}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✏️ Ввести своё количество", callback_data="stars_custom")])
    rows.append([InlineKeyboardButton(text="🔙 Назад",                   callback_data="back_main")])
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
    old_msg_id: int | None,
    text: str,
    reply_markup=None,
    parse_mode: str = "HTML"
) -> types.Message:
    """Удаляет старое сообщение и отправляет новое."""
    if old_msg_id:
        try:
            await bot.delete_message(chat_id, old_msg_id)
        except Exception:
            pass
    return await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)

# ─── BOT ──────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# ─── /start ───────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(msg: types.Message, state: FSMContext):
    await state.clear()
    data = await state.get_data()
    old  = data.get("last_msg_id")
    if await is_subscribed(bot, msg.from_user.id):
        sent = await replace_message(
            bot, msg.chat.id, old,
            "🏪 <b>chprrshop — главное меню</b>\n\nВыберите нужный раздел:",
            reply_markup=main_keyboard()
        )
    else:
        sent = await replace_message(
            bot, msg.chat.id, old,
            "👋 <b>Добро пожаловать в chprrshop!</b>\n\n"
            "Для использования бота необходимо подписаться на наш канал.\n"
            "Там вы найдёте актуальные предложения, акции и новинки.\n\n"
            "⬇️ Нажмите <b>«Подписаться»</b>, а затем <b>«Я подписался»</b>.",
            reply_markup=sub_keyboard()
        )
    await state.update_data(last_msg_id=sent.message_id)
    # Удалим сообщение /start пользователя
    try:
        await msg.delete()
    except Exception:
        pass

async def show_main(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    old  = data.get("last_msg_id")
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        "🏪 <b>chprrshop — главное меню</b>\n\nВыберите нужный раздел:",
        reply_markup=main_keyboard()
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

# ─── CHECK SUB ────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "check_sub")
async def check_sub(cb: types.CallbackQuery, state: FSMContext):
    if await is_subscribed(bot, cb.from_user.id):
        await cb.answer("✅ Подписка подтверждена!")
        await show_main(cb, state)
    else:
        await cb.answer("❌ Вы ещё не подписаны. Подпишитесь и попробуйте снова.", show_alert=True)

# ─── BACK MAIN ────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "back_main")
async def back_main(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_main(cb, state)

# ─── STARS MENU ───────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "menu_stars")
async def menu_stars(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    old  = data.get("last_msg_id")
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
    price  = calc_stars_price(amount)
    await state.update_data(stars_amount=amount, stars_price=price)
    await state.set_state(OrderStars.waiting_username)
    data = await state.get_data()
    old  = data.get("last_msg_id")
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
    await state.update_data(stars_amount=None, stars_price=None)
    await state.set_state(OrderStars.waiting_amount)
    data = await state.get_data()
    old  = data.get("last_msg_id")
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
        old  = data.get("last_msg_id")
        sent = await replace_message(
            bot, msg.chat.id, old,
            "❗️ Введите целое положительное число, например: <code>643</code>",
            reply_markup=back_kb("menu_stars")
        )
        await state.update_data(last_msg_id=sent.message_id)
        return
    amount = int(msg.text)
    price  = calc_stars_price(amount)
    await state.update_data(stars_amount=amount, stars_price=price)
    await state.set_state(OrderStars.waiting_username)
    data = await state.get_data()
    old  = data.get("last_msg_id")
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
    data     = await state.get_data()
    amount   = data.get("stars_amount")
    price    = data.get("stars_price")
    username = msg.text.strip()
    old      = data.get("last_msg_id")

    # Сохраняем заявку и переходим к ожиданию чека
    await state.update_data(order_username=username, order_type="stars")

    # Уведомляем АДМИНА
    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Новая заявка — Звёзды</b>\n\n"
        f"👤 Покупатель: @{msg.from_user.username or msg.from_user.id} (ID: <code>{msg.from_user.id}</code>)\n"
        f"⭐️ Количество: <b>{amount}</b>\n"
        f"💰 Сумма: <b>{price} грн</b>\n"
        f"📩 Получатель: <code>{username}</code>\n\n"
        f"Для подтверждения отправь карту покупателю командой:\n"
        f"<code>/confirm {msg.from_user.id}</code>",
        parse_mode="HTML"
    )

    await state.set_state(OrderStars.waiting_receipt)
    sent = await replace_message(
        bot, msg.chat.id, old,
        f"✅ <b>Заявка отправлена!</b>\n\n"
        f"⭐️ Звёзды: <b>{amount}</b>\n"
        f"💰 Сумма: <b>{price} грн</b>\n"
        f"👤 Получатель: <code>{username}</code>\n\n"
        "⏳ Ожидайте подтверждения от менеджера — он пришлёт реквизиты для оплаты.",
        reply_markup=back_kb("back_main")
    )
    await state.update_data(last_msg_id=sent.message_id)

# ─── PREMIUM MENU ─────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "menu_premium")
async def menu_premium(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    old  = data.get("last_msg_id")
    sent = await replace_message(
        bot, cb.message.chat.id, old,
        "💎 <b>Telegram Premium</b>\n\nВыберите срок подписки:",
        reply_markup=premium_keyboard()
    )
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data.startswith("premium_"))
async def premium_pick(cb: types.CallbackQuery, state: FSMContext):
    key          = cb.data.split("_")[1]
    label, price = PREMIUM_PRICES[key]
    await state.update_data(premium_label=label, premium_price=price)
    await state.set_state(OrderPremium.waiting_username)
    data = await state.get_data()
    old  = data.get("last_msg_id")
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
    data     = await state.get_data()
    label    = data.get("premium_label")
    price    = data.get("premium_price")
    username = msg.text.strip()
    old      = data.get("last_msg_id")

    await state.update_data(order_username=username, order_type="premium")

    # Уведомляем АДМИНА
    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Новая заявка — Premium</b>\n\n"
        f"👤 Покупатель: @{msg.from_user.username or msg.from_user.id} (ID: <code>{msg.from_user.id}</code>)\n"
        f"💎 Тариф: <b>{label}</b>\n"
        f"💰 Сумма: <b>{price} грн</b>\n"
        f"📩 Получатель: <code>{username}</code>\n\n"
        f"Для подтверждения отправь карту покупателю командой:\n"
        f"<code>/confirm {msg.from_user.id}</code>",
        parse_mode="HTML"
    )

    await state.set_state(OrderPremium.waiting_receipt)
    sent = await replace_message(
        bot, msg.chat.id, old,
        f"✅ <b>Заявка отправлена!</b>\n\n"
        f"💎 Telegram Premium: <b>{label}</b>\n"
        f"💰 Сумма: <b>{price} грн</b>\n"
        f"👤 Получатель: <code>{username}</code>\n\n"
        "⏳ Ожидайте подтверждения от менеджера — он пришлёт реквизиты для оплаты.",
        reply_markup=back_kb("back_main")
    )
    await state.update_data(last_msg_id=sent.message_id)

# ─── ADMIN /confirm ───────────────────────────────────────────────────────────
@dp.message(F.text.startswith("/confirm"))
async def admin_confirm(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("Использование: /confirm <user_id>")
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        await msg.answer("Неверный user_id.")
        return

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
    await msg.answer(f"✅ Реквизиты отправлены пользователю {user_id}.")

# ─── RECEIPT FLOW ─────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "send_receipt")
async def ask_receipt(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    old  = data.get("last_msg_id")
    # Определяем, в каком state-режиме находится пользователь
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
    try:
        await msg.delete()
    except Exception:
        pass
    old = data.get("last_msg_id")

    # Пересылаем чек админу
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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
