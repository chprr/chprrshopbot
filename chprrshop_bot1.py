import asyncio
import logging
import math
import os
import json
import re
import asyncpg
from aiogram import Bot, Dispatcher, types, F, filters
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, WebAppInfo
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

SUPPORT_USERNAME = "@chprr"

# Динамические конфигурационные глобальные переменные (кэш БД)
CARD_NUMBER = "4874 0700 5861 6069"
STAR_PRICE = 0.80  
WEBAPP_URL = "https://example.com"
STARS_OPTIONS = [50, 100, 200, 250, 500, 1000]
PREMIUM_PRICES = {
    "3": {"duration_ru": "3 месяца", "duration_uk": "3 місяці", "price": 550},
    "6": {"duration_ru": "6 месяцев", "duration_uk": "6 місяців", "price": 740},
    "12": {"duration_ru": "1 год", "duration_uk": "1 рік", "price": 1290},
}

# ─── ЛОКАЛИЗАЦИЯ / ЛОКАЛІЗАЦІЯ ────────────────────────────────────────────────
TEXTS = {
    "ru": {
        "main_menu": "🏪 <b>chprrshop — главное меню</b>\n\nВыберите нужный раздел:",
        "sub_required": "👋 <b>Добро пожаловать в chprrshop!</b>\n\nДля использования бота необходимо подписаться на наш канал.\nТам вы найдёте актуальные предложения, акции и новинки.\n\n⬇️ Нажмите <b>«Подписаться»</b>, а затем <b>«Я подписался»</b>.",
        "btn_stars": "⭐️ Звёзды",
        "btn_premium": "💎 Telegram Premium",
        "btn_reviews": "💬 Отзывы",
        "btn_conditions": "📋 Условия покупки",
        "btn_channel": "📢 Телеграм канал",
        "btn_lang": "🌍 Язык / Мова",
        "btn_sub": "📢 Подписаться на канал",
        "btn_is_subbed": "✅ Я подписался",
        "sub_confirmed": "✅ Подписка подтверждена!",
        "sub_not_yet": "❌ Вы ещё не подписаны. Подпишитесь и попробуйте снова.",
        "stars_title": "⭐️ <b>Покупка Telegram Stars</b>\n\nВыберите количество звёзд или введите своё:",
        "stars_selected": "⭐️ Выбрано: <b>{amount} звёзд — {price} грн</b>\n\nВведите username получателя:",
        "stars_custom_prompt": "✏️ Введите желаемое количество звёзд (минимально: 50):\n\n💡 Цена рассчитывается автоматически.",
        "stars_min_error": "❗️ Минимальное количество звёзд для заказа — <b>50</b>. Введите корректное число:",
        "stars_custom_qty": "⭐️ Количество: <b>{amount} звёзд</b>\n💰 Стоимость: <b>{price} грн</b>\n\nВведите username получателя:",
        "username_error": "❗️ <b>Ошибка: Имя должно быть только на английском языке!</b>\n\n⭐️ Выбрано: <b>{amount} звёзд — {price} грн</b>\n\nВведите корректный username получателя:",
        "verify_title": "📋 <b>Проверка данных заказа</b>\n\n⭐️ Товар: <b>{item}</b>\n💰 Сумма к оплате: <b>{price} грн</b>\n📩 Получатель: <code>{recipient}</code>\n\nПроверьте правильность данных и нажмите кнопку подтверждения:",
        "btn_verify_confirm": "✅ Все верно, заказать",
        "btn_verify_change": "🔙 Изменить юзернейм",
        "order_sent": "✅ <b>Заявка отправлена!</b>\n\n⭐️ Товар: <b>{item}</b>\n💰 Сумма: <b>{price} грн</b>\n👤 Получатель: <code>{recipient}</code>\n\n⏳ Ожидайте подтверждения от менеджера — он пришлёт реквизиты для оплаты.",
        "premium_title": "💎 <b>Telegram Premium</b>\n\nВыберите срок подписки:",
        "premium_selected": "💎 Выбрано: <b>Telegram Premium {label} — {price} грн</b>\n\nВведите username получателя:",
        "premium_username_error": "❗️ <b>Ошибка: Имя должно быть только на английском языке!</b>\n\n💎 Выбрано: <b>Telegram Premium {label} — {price} грн</b>\n\nВведите корректный username получателя:",
        "admin_confirmed": "✅ <b>Ваша заявка подтверждена!</b>\n\n💳 Для оплаты переведите ровно <b>{price} грн</b> на карту:\n<code>{CARD_NUMBER}</code>\n\nПосле оплаты нажмите <b>«Я оплатил»</b> и отправьте скриншот/чек.",
        "btn_i_paid": "✅ Я оплатил — отправить чек",
        "admin_declined": "❌ <b>Ваш заказ отклонен менеджером</b>\n\n📝 Причина: <code>{reason}</code>\n\n📞 Обратная связь: {SUPPORT_USERNAME}",
        "admin_completed": "🎉 <b>Ваш заказ успешно выполнен!</b>\n\nСпасибо, что выбрали нас. Пожалуйста, оставьте отзыв о нашей работе, нажав на кнопку ниже:",
        "btn_leave_review": "💬 Оставить отзыв",
        "ask_receipt": "📎 <b>Отправьте чек или скриншот оплаты</b>\n\nПрикрепите фото или документ с подтверждением оплаты:",
        "receipt_received": "🎉 <b>Чек получен!</b>\n\nМенеджер проверит платёж и доставит товар в ближайшее время.",
        "review_prompt": "📝 Напишите ваш отзыв в одном сообщении, и он автоматически опубликуется в нашем канале:",
        "review_thanks": "❤️ <b>Спасибо за ваш отзыв!</b> Он успешно опубликован в канале отзывов.",
        "review_error": "❌ Не удалось отправить отзыв в канал. Связывайтесь с администрацией.",
        "back": "🔙 Назад",
        "stars_item": "{amount} Звёзд",
        "premium_item": "Telegram Premium {label}"
    },
    "uk": {
        "main_menu": "🏪 <b>chprrshop — головне меню</b>\n\nОберіть потрібний розділ:",
        "sub_required": "👋 <b>Ласкаво просимо до chprrshop!</b>\n\nДля використання бота необхідно підписатися на наш канал.\nТам ви знайдете актуальні пропозиції, акції та новинки.\n\n⬇️ Натисніть <b>«Підписатися»</b>, а затем <b>«Я підписався»</b>.",
        "btn_stars": "⭐️ Зірки",
        "btn_premium": "💎 Telegram Premium",
        "btn_reviews": "💬 Відгуки",
        "btn_conditions": "📋 Uмови замовлення",
        "btn_channel": "📢 Підписатися на канал",
        "btn_lang": "🌍 Мова / Язык",
        "btn_sub": "📢 Підписатися на канал",
        "btn_is_subbed": "✅ Я підписався",
        "sub_confirmed": "✅ Підписку підтверджено!",
        "sub_not_yet": "❌ Ви ще не підписані. Підпишіться та спробуйте знову.",
        "stars_title": "⭐️ <b>Купівля Telegram Stars</b>\n\nОберіть кількість зірок або введіть свою кількість:",
        "stars_selected": "⭐️ Обрано: <b>{amount} зірок — {price} грн</b>\n\nВведіть username отримувача:",
        "stars_custom_prompt": "✏️ Введіть бажану кількість зірок (мінімально: 50):\n\n💡 Ціна розраховується автоматично.",
        "stars_min_error": "❗️ Мінімальна кількість зірок для замовлення — <b>50</b>. Введіть коректне число:",
        "stars_custom_qty": "⭐️ Кількість: <b>{amount} зірок</b>\n💰 Вартість: <b>{price} грн</b>\n\nВведіть username отримувача:",
        "username_error": "❗️ <b>Помилка: Ім'я має бути тільки англійською мовою!</b>\n\n⭐️ Обрано: <b>{amount} зірок — {price} грн</b>\n\nВведіть коректний username отримувача:",
        "verify_title": "📋 <b>Перевірка данных замовлення</b>\n\n⭐️ Товар: <b>{item}</b>\n💰 Сума до оплати: <b>{price} грн</b>\n📩 Отримувач: <code>{recipient}</code>\n\nПеревірте правильність даних та натисніть кнопку підтвердження:",
        "btn_verify_confirm": "✅ Все правильно, замовити",
        "btn_verify_change": "🔙 Змінити юзернейм",
        "order_sent": "✅ <b>Заявку відправлено!</b>\n\n⭐️ Товар: <b>{item}</b>\n💰 Сума: <b>{price} грн</b>\n👤 Отримувач: <code>{recipient}</code>\n\n⏳ Очікуйте підтвердження від менеджера — він надішле реквізити для оплати.",
        "premium_title": "💎 <b>Telegram Premium</b>\n\nОберіть термін підписки:",
        "premium_selected": "💎 Обрано: <b>Telegram Premium {label} — {price} грн</b>\n\nВведіть username отримувача:",
        "premium_username_error": "❗️ <b>Помилка: Ім'я має бути тільки англійською мовою!</b>\n\n💎 Обрано: <b>Telegram Premium {label} — {price} грн</b>\n\nВведіть коректний username отримувача:",
        "admin_confirmed": "✅ <b>Ваша заявка підтверджена!</b>\n\n💳 Для оплати перекажіть рівно <b>{price} грн</b> на картку:\n<code>{CARD_NUMBER}</code>\n\nПісля оплати натисніть <b>«Я оплатив»</b> та надішліть скріншот/чек.",
        "btn_i_paid": "✅ Я оплатил — надіслати чек",
        "admin_declined": "❌ <b>Ваше замовлення відхилено менеджером</b>\n\n📝 Причина: <code>{reason}</code>\n\n📞 Зворотний зв'язок: {SUPPORT_USERNAME}",
        "admin_completed": "🎉 <b>Ваше замовлення успішно виконано!</b>\n\nДякуємо, що обрали нас. Будь ласка, залиште відгук про нашу роботу, натиснувши на кнопку ниже:",
        "btn_leave_review": "💬 Залишити відгук",
        "ask_receipt": "📎 <b>Надішліть чек або скріншот оплати</b>\n\nПрикріпіть фото або документ з підтвердженням оплати:",
        "receipt_received": "🎉 <b>Чек отримано!</b>\n\nМенеджер перевірить платіж та доставить товар найближчим часом.",
        "review_prompt": "📝 Напишіть ваш відгук в одному повідомленні, і він автоматично опублікується в нашому канале:",
        "review_thanks": "❤️ <b>Дякуємо за ваш відгук!</b> Його успішно опубліковано в каналі відгуків.",
        "review_error": "❌ Не вдалося відправити відгук в канал. Зв'яжіться з адміністрацією.",
        "back": "🔙 Назад",
        "stars_item": "{amount} Зірок",
        "premium_item": "Telegram Premium {label}"
    }
}

# ─── DATABASE SYSTEM (POSTGRESQL CONFIG SYNC) ─────────────────────────────────
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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                id INT PRIMARY KEY,
                card_number TEXT,
                star_price NUMERIC,
                webapp_url TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS stars_options (
                amount INT PRIMARY KEY,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS premium_tariffs (
                key TEXT PRIMARY KEY,
                label_ru TEXT,
                label_uk TEXT,
                price INT,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        
        # Наполнение базовыми дефолтными настройками, если таблицы пустые
        settings_exist = await conn.fetchval("SELECT COUNT(*) FROM bot_settings WHERE id = 1")
        if not settings_exist:
            await conn.execute("INSERT INTO bot_settings (id, card_number, star_price, webapp_url) VALUES (1, '4874 0700 5861 6069', 0.80, 'https://example.com')")
            
        stars_exist = await conn.fetchval("SELECT COUNT(*) FROM stars_options")
        if not stars_exist:
            for amt in [50, 100, 200, 250, 500, 1000]:
                await conn.execute("INSERT INTO stars_options (amount, is_active) VALUES ($1, TRUE)", amt)
                
        premium_exist = await conn.fetchval("SELECT COUNT(*) FROM premium_tariffs")
        if not premium_exist:
            await conn.execute("INSERT INTO premium_tariffs (key, label_ru, label_uk, price) VALUES ('3', '3 месяца', '3 місяці', 550)")
            await conn.execute("INSERT INTO premium_tariffs (key, label_ru, label_uk, price) VALUES ('6', '6 месяцев', '6 місяців', 740)")
            await conn.execute("INSERT INTO premium_tariffs (key, label_ru, label_uk, price) VALUES ('12', '1 год', '1 рік', 1290)")
            
        await conn.close()
        logging.info("✅ База даних PostgreSQL и конфигурационные таблицы успешно инициализированы.")
    except Exception as e:
        logging.error(f"❌ Помилка ініціалізації бази даних: {e}")

async def sync_config_globals():
    """Синхронизирует данные из PostgreSQL в глобальную оперативную память бота."""
    global CARD_NUMBER, STAR_PRICE, WEBAPP_URL, STARS_OPTIONS, PREMIUM_PRICES
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        settings = await conn.fetchrow("SELECT card_number, star_price, webapp_url FROM bot_settings WHERE id = 1")
        if settings:
            CARD_NUMBER = settings['card_number']
            STAR_PRICE = float(settings['star_price'])
            WEBAPP_URL = settings['webapp_url']
            
        stars_rows = await conn.fetch("SELECT amount FROM stars_options WHERE is_active = TRUE ORDER BY amount ASC")
        if stars_rows:
            STARS_OPTIONS = [r['amount'] for r in stars_rows]
            
        prem_rows = await conn.fetch("SELECT key, label_ru, label_uk, price FROM premium_tariffs WHERE is_active = TRUE")
        if prem_rows:
            new_prem = {}
            for r in prem_rows:
                new_prem[r['key']] = {"duration_ru": r['label_ru'], "duration_uk": r['label_uk'], "price": r['price']}
            PREMIUM_PRICES = new_prem
            
        await conn.close()
        logging.info("⚙️ Глобальный кэш конфигурации из БД успешно синхронизирован.")
    except Exception as e:
        logging.error(f"❌ Ошибка синхронизации кэша конфигурации: {e}")

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
    waiting_for_card = State()
    waiting_for_price = State()
    waiting_for_webapp = State()

class UserFeedback(StatesGroup):
    waiting_review = State()

# ─── HELPERS (DYNAMIC KEYBOARDS) ──────────────────────────────────────────────
async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return m.status not in ("left", "kicked", "banned")
    except Exception:
        return False

def calc_stars_price(amount: int) -> int:
    return math.ceil(amount * STAR_PRICE)

def main_keyboard(lang: str) -> InlineKeyboardMarkup:
    buttons = []
    # Если WebApp URL настроен и не является заглушкой, выводим кнопку приложения первой
    if WEBAPP_URL and WEBAPP_URL != "https://example.com":
        btn_text = "📱 Открыть магазин" if lang == "ru" else "📱 Відкрити магазин"
        buttons.append([InlineKeyboardButton(text=btn_text, web_app=WebAppInfo(url=WEBAPP_URL))])
        
    buttons.extend([
        [
            InlineKeyboardButton(text=TEXTS[lang]["btn_stars"], callback_data="menu_stars"),
            InlineKeyboardButton(text=TEXTS[lang]["btn_premium"], callback_data="menu_premium"),
        ],
        [
            InlineKeyboardButton(text=TEXTS[lang]["btn_reviews"], url=REVIEWS_URL),
            InlineKeyboardButton(text=TEXTS[lang]["btn_conditions"], url=CONDITIONS_URL),
        ],
        [
            InlineKeyboardButton(text=TEXTS[lang]["btn_channel"], url=CHANNEL_URL),
        ],
        [
            InlineKeyboardButton(text=TEXTS[lang]["btn_lang"], callback_data="change_lang"),
        ]
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def sub_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=TEXTS[lang]["btn_sub"], url=CHANNEL_URL)],
        [InlineKeyboardButton(text=TEXTS[lang]["btn_is_subbed"], callback_data="check_sub")],
    ])

def stars_keyboard(lang: str) -> InlineKeyboardMarkup:
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
    rows.append([InlineKeyboardButton(text="✏| " + TEXTS[lang]["stars_custom_prompt"].split("\n")[0].replace("✏️ ", ""), callback_data="stars_custom")])
    rows.append([InlineKeyboardButton(text=TEXTS[lang]["back"], callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def premium_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = []
    for key, data in PREMIUM_PRICES.items():
        label = data[f"duration_{lang}"]
        price = data["price"]
        rows.append([InlineKeyboardButton(
            text=f"💎 {label} — {price} грн",
            callback_data=f"premium_{key}"
        )])
    rows.append([InlineKeyboardButton(text=TEXTS[lang]["back"], callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def back_kb(cb: str = "back_main", lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=TEXTS[lang]["back"], callback_data=cb)]
    ])

# ─── SAFE EDIT / DELETE + SEND ────────────────────────────────────────────────
async def replace_message(bot: Bot, chat_id: int, old_msg_id, text: str, reply_markup=None, parse_mode: str = "HTML") -> types.Message:
    if old_msg_id:
        try: await bot.delete_message(chat_id, old_msg_id)
        except Exception: pass
    return await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)

async def show_lang_selection(chat_id: int, state: FSMContext):
    data = await state.get_data()
    old_id = data.get("last_msg_id")
    text = "🌍 <b>Выберите язык / Оберіть мову</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru"), InlineKeyboardButton(text="🇺🇦 Українська", callback_data="set_lang_uk")]
    ])
    sent = await replace_message(bot, chat_id, old_id, text, reply_markup=kb)
    await state.update_data(last_msg_id=sent.message_id)

async def send_main_page(chat_id: int, user_id: int, state: FSMContext):
    global cached_photo_id
    data = await state.get_data()
    lang = data.get("lang")
    if not lang:
        await show_lang_selection(chat_id, state)
        return

    old_id = data.get("last_msg_id")
    if old_id:
        try: await bot.delete_message(chat_id, old_id)
        except Exception: pass

    await state.set_state(None)
    await state.set_data({"lang": lang})

    if await is_subscribed(bot, user_id):
        main_text = TEXTS[lang]["main_menu"]
        if cached_photo_id:
            try: sent = await bot.send_photo(chat_id, photo=cached_photo_id, caption=main_text, reply_markup=main_keyboard(lang), parse_mode="HTML")
            except Exception: cached_photo_id = None

        if not cached_photo_id:
            if os.path.exists(LOCAL_PHOTO_PATH):
                try:
                    photo_file = FSInputFile(LOCAL_PHOTO_PATH)
                    sent = await bot.send_photo(chat_id, photo=photo_file, caption=main_text, reply_markup=main_keyboard(lang), parse_mode="HTML")
                    if sent.photo: cached_photo_id = sent.photo[-1].file_id
                except Exception as e:
                    logging.error(f"Error sending local photo: {e}")
                    sent = await bot.send_message(chat_id, main_text, reply_markup=main_keyboard(lang), parse_mode="HTML")
            else:
                sent = await bot.send_message(chat_id, main_text, reply_markup=main_keyboard(lang), parse_mode="HTML")
    else:
        sent = await bot.send_message(chat_id, TEXTS[lang]["sub_required"], reply_markup=sub_keyboard(lang), parse_mode="HTML")
    await state.update_data(last_msg_id=sent.message_id)

# ─── ADMIN SYSTEM PANELS (ANALYTICS & SETTINGS HANDLERS) ──────────────────────
@dp.message(filters.Command("admin"))
async def cmd_admin_panel(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика продаж", callback_data="admin_view_stats")],
        [InlineKeyboardButton(text="💳 Изменить карту", callback_data="admin_edit_card")],
        [InlineKeyboardButton(text="💰 Изменить курс звезд", callback_data="admin_edit_price")],
        [InlineKeyboardButton(text="🌐 Изменить WebApp URL", callback_data="admin_edit_webapp")]
    ])
    await msg.answer("🛠 <b>Панель администратора chprrshop</b>\n\nВыберите действие для настройки конфигураций и просмотра отчётов:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "admin_view_stats")
async def admin_view_stats(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        total_actions = await conn.fetchval("SELECT COUNT(*) FROM logs")
        completed_orders = await conn.fetchval("SELECT COUNT(*) FROM logs WHERE action = 'admin_completed_order'")
        stars_orders = await conn.fetchval("SELECT COUNT(*) FROM logs WHERE action = 'order_stars_created'")
        premium_orders = await conn.fetchval("SELECT COUNT(*) FROM logs WHERE action = 'order_premium_created'")
        unique_users = await conn.fetchval("SELECT COUNT(DISTINCT user_id) FROM logs")
        await conn.close()
        
        stats_text = (
            f"📊 <b>Аналитика и статистика продаж chprrshop</b>\n\n"
            f"👥 Уникальных пользователей в системе: <b>{unique_users}</b>\n"
            f"🔄 Всего логов/действий записано: <b>{total_actions}</b>\n\n"
            f"⭐️ Создано заявок на Звезды: <b>{stars_orders}</b>\n"
            f"💎 Создано заявок на Premium: <b>{premium_orders}</b>\n"
            f"🚀 <b>Успешно выполненных заказов: {completed_orders}</b>"
        )
        await cb.message.answer(stats_text, parse_mode="HTML")
    except Exception as e:
        await cb.message.answer(f"❌ Ошибка получения статистики: {e}")
    await cb.answer()

@dp.callback_query(F.data == "admin_edit_card")
async def admin_edit_card(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID: return
    await state.set_state(AdminWorkflow.waiting_for_card)
    await cb.message.answer("💳 Введите <b>новый номер карты</b> для оплаты:")
    await cb.answer()

@dp.message(AdminWorkflow.waiting_for_card)
async def admin_save_card(msg: types.Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    new_card = msg.text.strip()
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("UPDATE bot_settings SET card_number = $1 WHERE id = 1", new_card)
    await conn.close()
    await sync_config_globals()
    await state.clear()
    await msg.answer(f"✅ Номер карты успешно обновлен на: <code>{new_card}</code>", parse_mode="HTML")

@dp.callback_query(F.data == "admin_edit_price")
async def admin_edit_price(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID: return
    await state.set_state(AdminWorkflow.waiting_for_price)
    await cb.message.answer("💰 Введите <b>новый курс одной звезды</b> (например, <code>0.75</code>):")
    await cb.answer()

@dp.message(AdminWorkflow.waiting_for_price)
async def admin_save_price(msg: types.Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try:
        new_price = float(msg.text.strip())
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute("UPDATE bot_settings SET star_price = $1 WHERE id = 1", new_price)
        await conn.close()
        await sync_config_globals()
        await state.clear()
        await msg.answer(f"✅ Стоимость одной звезды успешно обновлена на: <b>{new_price} грн</b>", parse_mode="HTML")
    except ValueError:
        await msg.answer("❌ Ошибка: Введите корректное число (используйте точку в качестве разделителя).")

@dp.callback_query(F.data == "admin_edit_webapp")
async def admin_edit_webapp(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID: return
    await state.set_state(AdminWorkflow.waiting_for_webapp)
    await cb.message.answer("🌐 Введите <b>новый URL для Telegram WebApp Mini App</b>:")
    await cb.answer()

@dp.message(AdminWorkflow.waiting_for_webapp)
async def admin_save_webapp(msg: types.Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    new_url = msg.text.strip()
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("UPDATE bot_settings SET webapp_url = $1 WHERE id = 1", new_url)
    await conn.close()
    await sync_config_globals()
    await state.clear()
    await msg.answer(f"✅ Ссылка на WebApp успешно сохранена: <code>{new_url}</code>", parse_mode="HTML")

# ─── BOT STANDARD HANDLERS ────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("set_lang_"))
async def set_language(cb: types.CallbackQuery, state: FSMContext):
    lang = cb.data.split("_")[2]
    await state.update_data(lang=lang)
    await cb.answer("Язык интерфейса изменен!" if lang == "ru" else "Мову інтерфейсу змінено!")
    await send_main_page(cb.message.chat.id, cb.from_user.id, state)

@dp.callback_query(F.data == "change_lang")
async def change_lang_callback(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "change_lang")
    await show_lang_selection(cb.message.chat.id, state)
    await cb.answer()

@dp.callback_query(F.data == "check_sub")
async def check_sub(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "check_subscription")
    data = await state.get_data()
    lang = data.get("lang", "ru")
    if await is_subscribed(bot, cb.from_user.id):
        await cb.answer(TEXTS[lang]["sub_confirmed"])
        await send_main_page(cb.message.chat.id, cb.from_user.id, state)
    else:
        await cb.answer(TEXTS[lang]["sub_not_yet"], show_alert=True)

@dp.callback_query(F.data == "back_main")
async def back_main(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "back_to_main")
    await cb.answer()
    await send_main_page(cb.message.chat.id, cb.from_user.id, state)

@dp.callback_query(F.data == "back_from_username_stars")
async def back_from_username_stars(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    is_custom = data.get("is_custom", False)
    lang = data.get("lang", "ru")
    old = data.get("last_msg_id")
    if is_custom:
        await state.set_state(OrderStars.waiting_amount)
        sent = await replace_message(bot, cb.message.chat.id, old, TEXTS[lang]["stars_custom_prompt"], reply_markup=back_kb("menu_stars", lang))
        await state.update_data(last_msg_id=sent.message_id)
    else:
        await menu_stars(cb, state)
    await cb.answer()

@dp.callback_query(F.data == "menu_stars")
async def menu_stars(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "open_menu_stars")
    data = await state.get_data()
    lang = data.get("lang", "ru")
    old = data.get("last_msg_id")
    sent = await replace_message(bot, cb.message.chat.id, old, TEXTS[lang]["stars_title"], reply_markup=stars_keyboard(lang))
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data.startswith("stars_") & ~F.data.in_({"stars_custom"}))
async def stars_pick(cb: types.CallbackQuery, state: FSMContext):
    amount = int(cb.data.split("_")[1])
    price = calc_stars_price(amount)
    await log_action(cb.from_user.id, cb.from_user.username, "select_stars", {"amount": amount, "price": price})
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.update_data(stars_amount=amount, stars_price=price, is_custom=False)
    await state.set_state(OrderStars.waiting_username)
    old = data.get("last_msg_id")
    sent = await replace_message(bot, cb.message.chat.id, old, TEXTS[lang]["stars_selected"].format(amount=amount, price=price), reply_markup=back_kb("back_from_username_stars", lang))
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data == "stars_custom")
async def stars_custom(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "select_custom_stars")
    await state.set_state(OrderStars.waiting_amount)
    await state.update_data(is_custom=True)
    data = await state.get_data()
    lang = data.get("lang", "ru")
    old = data.get("last_msg_id")
    sent = await replace_message(bot, cb.message.chat.id, old, TEXTS[lang]["stars_custom_prompt"], reply_markup=back_kb("menu_stars", lang))
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.message(OrderStars.waiting_amount)
async def stars_custom_amount(msg: types.Message, state: FSMContext):
    try: await msg.delete()
    except Exception: pass
    data = await state.get_data()
    lang = data.get("lang", "ru")
    old = data.get("last_msg_id")
    if not msg.text.isdigit() or int(msg.text) < 50:
        sent = await replace_message(bot, msg.chat.id, old, TEXTS[lang]["stars_min_error"], reply_markup=back_kb("menu_stars", lang))
        await state.update_data(last_msg_id=sent.message_id)
        return
    amount = int(msg.text)
    price = calc_stars_price(amount)
    await log_action(msg.from_user.id, msg.from_user.username, "input_custom_stars", {"amount": amount, "price": price})
    await state.update_data(stars_amount=amount, stars_price=price)
    await state.set_state(OrderStars.waiting_username)
    sent = await replace_message(bot, msg.chat.id, old, TEXTS[lang]["stars_custom_qty"].format(amount=amount, price=price), reply_markup=back_kb("back_from_username_stars", lang))
    await state.update_data(last_msg_id=sent.message_id)

@dp.message(OrderStars.waiting_username)
async def stars_username(msg: types.Message, state: FSMContext):
    try: await msg.delete()
    except Exception: pass
    data = await state.get_data()
    lang = data.get("lang", "ru")
    amount = data.get("stars_amount")
    price = data.get("stars_price")
    old = data.get("last_msg_id")
    input_text = msg.text.strip().replace('@', '')
    if not re.match(r'^[a-zA-Z0-9_]+$', input_text):
        sent = await replace_message(bot, msg.chat.id, old, TEXTS[lang]["username_error"].format(amount=amount, price=price), reply_markup=back_kb("back_from_username_stars", lang))
        await state.update_data(last_msg_id=sent.message_id)
        return
    recipient_display = f"@{input_text}"
    await state.update_data(order_username=recipient_display, order_type="stars", client_id=msg.from_user.id, client_name=msg.from_user.username)
    await state.set_state(OrderStars.waiting_confirmation)
    verify_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=TEXTS[lang]["btn_verify_confirm"], callback_data="user_confirm_stars")],
        [InlineKeyboardButton(text=TEXTS[lang]["btn_verify_change"], callback_data="user_back_stars_username")]
    ])
    item_name = TEXTS[lang]["stars_item"].format(amount=amount)
    sent = await replace_message(bot, msg.chat.id, old, TEXTS[lang]["verify_title"].format(item=item_name, price=price, recipient=recipient_display), reply_markup=verify_markup)
    await state.update_data(last_msg_id=sent.message_id)

@dp.callback_query(F.data == "user_back_stars_username")
async def user_back_stars_username(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(OrderStars.waiting_username)
    data = await state.get_data()
    lang = data.get("lang", "ru")
    amount = data.get("stars_amount")
    price = data.get("stars_price")
    old = data.get("last_msg_id")
    sent = await replace_message(bot, cb.message.chat.id, old, TEXTS[lang]["stars_custom_qty"].format(amount=amount, price=price), reply_markup=back_kb("back_from_username_stars", lang))
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data == "user_confirm_stars")
async def user_confirm_stars(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    amount = data.get("stars_amount")
    price = data.get("stars_price")
    recipient_display = data.get("order_username")
    client_id = data.get("client_id")
    client_name = data.get("client_name")
    old = data.get("last_msg_id")
    await log_action(client_id, client_name, "order_stars_created", {"amount": amount, "price": price, "target_user": recipient_display})
    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить и отправить карту", callback_data=f"admin_confirm_{client_id}_{price}")],
        [InlineKeyboardButton(text="❌ Отклонить заказ", callback_data=f"admin_predecline_{client_id}")]
    ])
    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Новая заявка — Звёзды</b>\n\n👤 Покупатель: @{client_name or client_id} (ID: <code>{client_id}</code>)\n⭐️ Количество: <b>{amount}</b>\n💰 Сумма: <b>{price} грн</b>\n📩 Получатель: <code>{recipient_display}</code>\n🌐 Язык клиента: <b>{lang.upper()}</b>",
        reply_markup=admin_markup, parse_mode="HTML"
    )
    await state.set_state(OrderStars.waiting_receipt)
    item_name = TEXTS[lang]["stars_item"].format(amount=amount)
    sent = await replace_message(bot, cb.message.chat.id, old, TEXTS[lang]["order_sent"].format(item=item_name, price=price, recipient=recipient_display), reply_markup=back_kb("back_main", lang))
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

# ─── PREMIUM FLOW ─────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "menu_premium")
async def menu_premium(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "open_menu_premium")
    data = await state.get_data()
    lang = data.get("lang", "ru")
    old = data.get("last_msg_id")
    sent = await replace_message(bot, cb.message.chat.id, old, TEXTS[lang]["premium_title"], reply_markup=premium_keyboard(lang))
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data.startswith("premium_"))
async def premium_pick(cb: types.CallbackQuery, state: FSMContext):
    key = cb.data.split("_")[1]
    data = await state.get_data()
    lang = data.get("lang", "ru")
    label = PREMIUM_PRICES[key][f"duration_{lang}"]
    price = PREMIUM_PRICES[key]["price"]
    await log_action(cb.from_user.id, cb.from_user.username, "select_premium", {"duration": label, "price": price})
    await state.update_data(premium_price=price, premium_key=key)
    await state.set_state(OrderPremium.waiting_username)
    old = data.get("last_msg_id")
    sent = await replace_message(bot, cb.message.chat.id, old, TEXTS[lang]["premium_selected"].format(label=label, price=price), reply_markup=back_kb("menu_premium", lang))
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.message(OrderPremium.waiting_username)
async def premium_username(msg: types.Message, state: FSMContext):
    try: await msg.delete()
    except Exception: pass
    data = await state.get_data()
    lang = data.get("lang", "ru")
    key = data.get("premium_key")
    label = PREMIUM_PRICES[key][f"duration_{lang}"]
    price = data.get("premium_price")
    old = data.get("last_msg_id")
    input_text = msg.text.strip().replace('@', '')
    if not re.match(r'^[a-zA-Z0-9_]+$', input_text):
        sent = await replace_message(bot, msg.chat.id, old, TEXTS[lang]["premium_username_error"].format(label=label, price=price), reply_markup=back_kb("menu_premium", lang))
        await state.update_data(last_msg_id=sent.message_id)
        return
    recipient_display = f"@{input_text}"
    await state.update_data(order_username=recipient_display, order_type="premium", client_id=msg.from_user.id, client_name=msg.from_user.username)
    await state.set_state(OrderPremium.waiting_confirmation)
    verify_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=TEXTS[lang]["btn_verify_confirm"], callback_data="user_confirm_premium")],
        [InlineKeyboardButton(text=TEXTS[lang]["btn_verify_change"], callback_data="user_back_premium_username")]
    ])
    item_name = TEXTS[lang]["premium_item"].format(label=label)
    sent = await replace_message(bot, msg.chat.id, old, TEXTS[lang]["verify_title"].format(item=item_name, price=price, recipient=recipient_display), reply_markup=verify_markup)
    await state.update_data(last_msg_id=sent.message_id)

@dp.callback_query(F.data == "user_back_premium_username")
async def user_back_premium_username(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(OrderPremium.waiting_username)
    data = await state.get_data()
    lang = data.get("lang", "ru")
    key = data.get("premium_key")
    label = PREMIUM_PRICES[key][f"duration_{lang}"]
    price = data.get("premium_price")
    old = data.get("last_msg_id")
    sent = await replace_message(bot, cb.message.chat.id, old, TEXTS[lang]["premium_selected"].format(label=label, price=price), reply_markup=back_kb("menu_premium", lang))
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.callback_query(F.data == "user_confirm_premium")
async def user_confirm_premium(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    key = data.get("premium_key")
    label_ru = PREMIUM_PRICES[key]["duration_ru"]
    label_lang = PREMIUM_PRICES[key][f"duration_{lang}"]
    price = data.get("premium_price")
    recipient_display = data.get("order_username")
    client_id = data.get("client_id")
    client_name = data.get("client_name")
    old = data.get("last_msg_id")
    await log_action(client_id, client_name, "order_premium_created", {"duration": label_ru, "price": price, "target_user": recipient_display})
    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить и отправить карту", callback_data=f"admin_confirm_{client_id}_{price}")],
        [InlineKeyboardButton(text="❌ Отклонить заказ", callback_data=f"admin_predecline_{client_id}")]
    ])
    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Новая заявка — Premium</b>\n\n👤 Покупатель: @{client_name or client_id} (ID: <code>{client_id}</code>)\n💎 Тариф: <b>{label_ru}</b>\n💰 Сумма: <b>{price} грн</b>\n📩 Получатель: <code>{recipient_display}</code>\n🌐 Язык клиента: <b>{lang.upper()}</b>",
        reply_markup=admin_markup, parse_mode="HTML"
    )
    await state.set_state(OrderPremium.waiting_receipt)
    item_name = TEXTS[lang]["premium_item"].format(label=label_lang)
    sent = await replace_message(bot, cb.message.chat.id, old, TEXTS[lang]["order_sent"].format(item=item_name, price=price, recipient=recipient_display), reply_markup=back_kb("back_main", lang))
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

# ─── ADMIN ORDER CONFIRM / REJECT UTILITIES ───────────────────────────────────
@dp.callback_query(F.data.startswith("admin_confirm_"))
async def admin_confirm_cb(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    parts = cb.data.split("_")
    user_id = int(parts[2])
    price = parts[3] if len(parts) > 3 else "нужную"
    await log_action(cb.from_user.id, cb.from_user.username, "admin_confirmed_order", {"client_id": user_id, "price": price})
    client_state = dp.fsm.get_context(bot, chat_id=user_id, user_id=user_id)
    client_data = await client_state.get_data()
    client_lang = client_data.get("lang", "ru")
    await bot.send_message(user_id, TEXTS[client_lang]["admin_confirmed"].format(price=price, CARD_NUMBER=CARD_NUMBER), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=TEXTS[client_lang]["btn_i_paid"], callback_data="send_receipt")]]), parse_mode="HTML")
    await cb.message.edit_text(cb.message.html_text + f"\n\n✅ <i>Реквизиты на сумму {price} грн отправлены пользователю! Ожидаем чек...</i>", reply_markup=None, parse_mode="HTML")
    await cb.answer()

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

@dp.callback_query(F.data.startswith("admin_decline_cancel_"))
async def admin_decline_cancel(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    user_id = int(cb.data.split("_")[3])
    base_text = cb.message.html_text.split("\n\n⚠️")[0]
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
    client_state = dp.fsm.get_context(bot, chat_id=user_id, user_id=user_id)
    client_data = await client_state.get_data()
    client_lang = client_data.get("lang", "ru")
    await bot.send_message(user_id, TEXTS[client_lang]["admin_declined"].format(reason=reason, SUPPORT_USERNAME=SUPPORT_USERNAME), parse_mode="HTML")
    try: await bot.edit_message_text(chat_id=ADMIN_ID, message_id=old_msg_id, text=old_text + f"\n\n❌ <b>Заказ отклонён. Причина:</b> {reason}", parse_mode="HTML")
    except Exception: pass
    await state.clear()
    await msg.reply("✅ <b>Клиент успешно уведомлен об отказе.</b>", parse_mode="HTML")

@dp.callback_query(F.data.startswith("admin_complete_"))
async def admin_complete_order(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    user_id = int(cb.data.split("_")[2])
    await log_action(ADMIN_ID, cb.from_user.username, "admin_completed_order", {"client_id": user_id})
    client_state = dp.fsm.get_context(bot, chat_id=user_id, user_id=user_id)
    client_data = await client_state.get_data()
    client_lang = client_data.get("lang", "ru")
    await bot.send_message(user_id, TEXTS[client_lang]["admin_completed"], reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=TEXTS[client_lang]["btn_leave_review"], callback_data="user_leave_review")]]), parse_mode="HTML")
    await cb.message.edit_text(cb.message.html_text + "\n\n🚀 <b>Заказ выполнен! Клиенту отправлено уведомление.</b>", reply_markup=None, parse_mode="HTML")
    await cb.answer("Заказ помечен как выполненный!")

# ─── RECEIPT & REVIEW FLOW ────────────────────────────────────────────────────
@dp.callback_query(F.data == "send_receipt")
async def ask_receipt(cb: types.CallbackQuery, state: FSMContext):
    await log_action(cb.from_user.id, cb.from_user.username, "clicked_i_paid")
    data = await state.get_data()
    lang = data.get("lang", "ru")
    old = data.get("last_msg_id")
    sent = await replace_message(bot, cb.message.chat.id, old, TEXTS[lang]["ask_receipt"], reply_markup=back_kb("back_main", lang))
    await state.update_data(last_msg_id=sent.message_id, waiting_receipt=True)
    await cb.answer()

@dp.message(F.photo | F.document)
async def receive_receipt(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("waiting_receipt"): return
    lang = data.get("lang", "ru")
    await log_action(msg.from_user.id, msg.from_user.username, "sent_receipt", {"order_type": data.get("order_type")})
    try: await msg.delete()
    except Exception: pass
    old = data.get("last_msg_id")
    client_id = data.get("client_id", msg.from_user.id)
    caption = f"💰 <b>Чек оплаты получен!</b>\n👤 Покупатель: @{msg.from_user.username or '—'} (ID: <code>{client_id}</code>)\n📩 Получатель: <code>{data.get('order_username', '—')}</code>"
    complete_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Заказ выполнен", callback_data=f"admin_complete_{client_id}")]])
    try:
        if msg.photo: await bot.send_photo(ADMIN_ID, msg.photo[-1].file_id, caption=caption, reply_markup=complete_markup, parse_mode="HTML")
        elif msg.document: await bot.send_document(ADMIN_ID, msg.document.file_id, caption=caption, reply_markup=complete_markup, parse_mode="HTML")
    except Exception as e: logging.error(f"Error forwarding receipt: {e}")
    await state.update_data(waiting_receipt=False)
    sent = await replace_message(bot, msg.chat.id, old, TEXTS[lang]["receipt_received"], reply_markup=main_keyboard(lang))
    await state.update_data(last_msg_id=sent.message_id)

@dp.callback_query(F.data == "user_leave_review")
async def user_pre_review(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserFeedback.waiting_review)
    data = await state.get_data()
    lang = data.get("lang", "ru")
    sent = await bot.send_message(cb.message.chat.id, TEXTS[lang]["review_prompt"], parse_mode="HTML")
    await state.update_data(last_msg_id=sent.message_id)
    await cb.answer()

@dp.message(UserFeedback.waiting_review)
async def user_input_review(msg: types.Message, state: FSMContext):
    review_text = msg.text.strip()
    user_name = f"@{msg.from_user.username}" if msg.from_user.username else "Клиент"
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await log_action(msg.from_user.id, msg.from_user.username, "left_review")
    try:
        await bot.send_message(chat_id=REVIEWS_CHANNEL, text=f"💬 <b>Новый отзыв от {user_name}:</b>\n\n«{review_text}»\n\n🏪 @chprrshop", parse_mode="HTML")
        await msg.reply(TEXTS[lang]["review_thanks"], parse_mode="HTML")
    except Exception as e:
        logging.error(f"Error publishing review: {e}")
        await msg.reply(TEXTS[lang]["review_error"], parse_mode="HTML")
    await state.set_state(None)
    await state.set_data({"lang": lang})
    await send_main_page(msg.chat.id, msg.from_user.id, state)

# ─── RUN ──────────────────────────────────────────────────────────────────────
async def main():
    await init_db()
    await sync_config_globals()  # Синхронизируем настройки из базы данных в кэш бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())