import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Токен вашего бота (лучше настроить через Environment Variables на Render)
TOKEN = "8376223950:AAE4GEMYTlBtVWz80cBuUyiblVZ9_wymFXo"
ADMIN_ID = 8859438543  # Укажите ваш Telegram ID для уведомлений о покупках

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    # Таблица пользователей и анкет
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            age INTEGER,
            gender TEXT,
            is_premium INTEGER DEFAULT 0,
            complaints INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            msgs_sent INTEGER DEFAULT 0,
            msgs_received INTEGER DEFAULT 0
        )
    """)
    # Очередь поиска
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            user_id INTEGER PRIMARY KEY
        )
    """)
    # Активные чаты
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_chats (
            user1 INTEGER,
            user2 INTEGER
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- FSM ДЛЯ РЕГИСТРАЦИИ ---
class RegisterState(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_gender = State()


dp = Dispatcher(storage=MemoryStorage())

# Клавиатуры
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔎 Найти собеседника")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="⭐ Купить Премиум")],
        [KeyboardButton(text="❌ Остановить диалог")]
    ],
    resize_keyboard=True
)

skip_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="⏭ Пропустить")]],
    resize_keyboard=True
)

gender_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Мат."), KeyboardButton(text="Жен.")],
        [KeyboardButton(text="⏭ Пропустить")]
    ],
    resize_keyboard=True
)

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Проверка на бан
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row[0] == 1:
        conn.close()
        await message.answer("❌ Вы заблокированы в этом боте за большое количество жалоб.")
        return

    # Проверяем, есть ли уже в базе
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()
    conn.close()

    if not exists:
        await message.answer("Привет! Добро пожаловать в анонимный чат.\nДавай заполним небольшую анкету. Как тебя зовут (или какой псевдоним)?", reply_markup=skip_kb)
        await state.set_state(RegisterState.waiting_for_name)
    else:
        await message.answer("С возвращением! Главное меню:", reply_markup=main_kb)

@dp.message(RegisterState.waiting_for_name, F.text)
async def process_name(message: Message, state: FSMContext):
    name = None if message.text == "⏭ Пропустить" else message.text
    await state.update_data(name=name)
    await message.answer("Сколько тебе лет?", reply_markup=skip_kb)
    await state.set_state(RegisterState.waiting_for_age)

@dp.message(RegisterState.waiting_for_age, F.text)
async def process_age(message: Message, state: FSMContext):
    age = None
    if message.text != "⏭ Пропустить":
        if message.text.isdigit():
            age = int(message.text)
        else:
            await message.answer("Пожалуйста, введи возраст цифрами или нажми «Пропустить».")
            return
    await state.update_data(age=age)
    await message.answer("Укажи свой пол:", reply_markup=gender_kb)
    await state.set_state(RegisterState.waiting_for_gender)

@dp.message(RegisterState.waiting_for_gender, F.text)
async def process_gender(message: Message, state: FSMContext):
    gender = None
    if message.text != "⏭ Пропустить":
        gender = message.text

    data = await state.get_data()
    name = data.get("name")
    age = data.get("age")
    user_id = message.from_user.id

    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (user_id, name, age, gender, is_premium, complaints, is_banned, msgs_sent, msgs_received)
        -- Сохраняем старые данные, если они были, или создаем новые
        VALUES (?, ?, ?, ?, 
            COALESCE((SELECT is_premium FROM users WHERE user_id = ?), 0),
            COALESCE((SELECT complaints FROM users WHERE user_id = ?), 0),
            COALESCE((SELECT is_banned FROM users WHERE user_id = ?), 0),
            COALESCE((SELECT msgs_sent FROM users WHERE user_id = ?), 0),
            COALESCE((SELECT msgs_received FROM users WHERE user_id = ?), 0)
        )
    """, (user_id, name, age, gender, user_id, user_id, user_id, user_id, user_id))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer("✅ Регистрация завершена! Добро пожаловать.", reply_markup=main_kb)


# --- ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ ---
@dp.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, age, gender, is_premium, complaints, msgs_sent, msgs_received FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await message.answer("Сначала пройдите регистрацию через /start")
        return

    name, age, gender, is_premium, complaints, sent, received = row
    status = "👑 Премиум (VIP)" if is_premium else "⭐ Обычный"

    text = (
        f"👤 **Ваш профиль:**\n\n"
        f"🏷 Имя: {name if name else 'Не указано'}\n"
        f"🎂 Возраст: {age if age else 'Не указан'}\n"
        f"🚻 Пол: {gender if gender else 'Не указан'}\n"
        f"💎 Статус: {status}\n\n"
        f"📊 **Статистика:**\n"
        f"💬 Отправлено сообщений: {sent}\n"
        f"📩 Получено сообщений: {received}\n"
        f"⚠️ Получено жалоб: {complaints} / 20"
    )
    await message.answer(text, parse_mode="Markdown")


# --- ПОКУПКА ПРЕМИУМА (TELEGRAM STARS) ---
@dp.message(F.text == "⭐ Купить Премиум")
async def buy_premium(message: Message):
    prices = [LabeledPrice(label="Премиум в анонимном чате", amount=100)]
    await message.answer_invoice(
        title="VIP Премиум-статус",
        description="Дает возможность видеть анкеты собеседников и другие бонусы!",
        payload="premium_sub",
        currency="XTR",
        prices=prices,
        start_parameter="buy_premium"
    )

@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: types.PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    await message.answer("🎉 Успешно! Вам активирован Премиум-статус 👑")
    try:
        await message.bot.send_message(ADMIN_ID, f"💰 Пользователь ID {user_id} купил Премиум за звёзды!")
    except Exception:
        pass


# --- ПОИСК СОБЕСЕДНИКА ---
@dp.message(F.text == "🔎 Найти собеседника")
async def search_companion(message: Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()

    # Проверка бана
    cursor.execute("SELECT is_banned, is_premium FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()
    if user_info and user_info[0] == 1:
        conn.close()
        await message.answer("❌ Вы заблокированы.")
        return
    
    is_premium = user_info[1] if user_info else 0

    # Проверка текущего чата
    cursor.execute("SELECT * FROM active_chats WHERE user1 = ? OR user2 = ?", (user_id, user_id))
    if cursor.fetchone():
        await message.answer("Вы уже в чате! Завершите текущий диалог.")
        conn.close()
        return

    # Ищем свободного в очереди
    cursor.execute("SELECT user_id FROM queue WHERE user_id != ?", (user_id,))
    companion = cursor.fetchone()

    if companion:
        companion_id = companion[0]
        cursor.execute("DELETE FROM queue WHERE user_id = ?", (companion_id,))
        cursor.execute("INSERT INTO active_chats VALUES (?, ?)", (user_id, companion_id))
        conn.commit()
        conn.close()

        # Функция для формирования текста анкеты собеседника для премиума
        async def get_companion_profile(target_id, viewer_is_premium):
            c = sqlite3.connect("chat.db")
            cur = c.cursor()
            cur.execute("SELECT name, age, gender FROM users WHERE user_id = ?", (target_id,))
            res = cur.fetchone()
            c.close()
            if not res:
                return "Анкета не найдена."
            c_name, c_age, c_gender = res
            if viewer_is_premium:
                return f"\n\n📋 **Анкета собеседника:**\n🏷 Имя: {c_name or 'Нет'}\n🎂 Возраст: {c_age or 'Нет'}\n🚻 Пол: {c_gender or 'Нет'}"
            else:
                return "\n\n🔒 *Хотите видеть анкету (имя, возраст, пол) собеседника? Купите Премиум!*"

        profile_for_user1 = await get_companion_profile(companion_id, is_premium)
        # Узнаем премиум-статус второго участника
        c2 = sqlite3.connect("chat.db")
        cur2 = c2.cursor()
        cur2.execute("SELECT is_premium FROM users WHERE user_id = ?", (companion_id,))
        comp_prem = cur2.fetchone()[0]
        c2.close()
        profile_for_user2 = await get_companion_profile(user_id, comp_prem)

        await message.answer(f"Собеседник найден! Общайтесь.{profile_for_user1}", parse_mode="Markdown")
        await message.bot.send_message(companion_id, f"Собеседник найден! Общайтесь.{profile_for_user2}", parse_mode="Markdown")
    else:
        cursor.execute("INSERT OR IGNORE INTO queue VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
        await message.answer("Ищем собеседника... Ожидайте ⏳")


# --- ОСТАНОВКА ДИАЛОГА И КНОПКИ ЖАЛОБ ---
@dp.message(F.text == "❌ Остановить диалог")
async def stop_chat(message: Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM queue WHERE user_id = ?", (user_id,))
    cursor.execute("SELECT user1, user2 FROM active_chats WHERE user1 = ? OR user2 = ?", (user_id, user_id))
    chat = cursor.fetchone()

    if chat:
        companion_id = chat[1] if chat[0] == user_id else chat[0]
        cursor.execute("DELETE FROM active_chats WHERE user1 = ? OR user2 = ?", (user_id, user_id))
        conn.commit()
        conn.close()

        # Клавиатура для оценки и жалобы
        rating_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👍 Отлично", callback_data=f"rate_good_{companion_id}"),
             InlineKeyboardButton(text="👎 Плохо", callback_data=f"rate_bad_{companion_id}")],
            [InlineKeyboardButton(text="⚠️ Пожаловаться", callback_data=f"complaint_{companion_id}")]
        ])

        await message.answer("Диалог завершен. Оцените собеседника:", reply_markup=rating_kb)
        try:
            await message.bot.send_message(companion_id, "Собеседник покинул чат. Оцените его:", reply_markup=rating_kb)
        except Exception:
            pass
        
        # Возвращаем обычную клаву меню
        await message.answer("Главное меню:", reply_markup=main_kb)
        try:
            await message.bot.send_message(companion_id, "Главное меню:", reply_markup=main_kb)
        except Exception:
            pass
    else:
        conn.commit()
        conn.close()
        await message.answer("Вы сейчас ни с кем не общаетесь.", reply_markup=main_kb)


# --- CALLBACK ДЛЯ РЕАКЦИЙ И ЖАЛОБ ---
@dp.callback_query(F.data.startswith("complaint_"))
async def process_complaint(callback: types.CallbackQuery):
    target_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    
    # Увеличиваем счетчик жалоб
    cursor.execute("UPDATE users SET complaints = complaints + 1 WHERE user_id = ?", (target_id,))
    cursor.execute("SELECT complaints FROM users WHERE user_id = ?", (target_id,))
    res = cursor.fetchone()
    complaints_count = res[0] if res else 0

    # Проверяем на автобан (20 жалоб)
    if complaints_count >= 20:
        cursor.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        try:
            await callback.bot.send_message(target_id, "❌ Вы были заблокированы в боте из-за большого количества жалоб.")
        except Exception:
            pass

    conn.commit()
    conn.close()

    await callback.answer("⚠️ Жалоба отправлена. Спасибо!", show_alert=True)
    await callback.message.edit_text("⚠️ Жалоба на собеседника успешно принята.")

@dp.callback_query(F.data.startswith("rate_"))
async def process_rating(callback: types.CallbackQuery):
    await callback.answer("Спасибо за вашу оценку!", show_alert=True)
    await callback.message.edit_text("✅ Диалог полностью закрыт. Оценка учтена.")


# --- ПЕРЕСЫЛКА СООБЩЕНИЙ МЕЖДУ СОБЕСЕДНИКАМИ ---
@dp.message()
async def forward_handler(message: Message):
    if message.text in ["🔎 Найти собеседника", "👤 Профиль", "⭐ Купить Премиум", "❌ Остановить диалог"] or message.text and message.text.startswith("/"):
        return

    user_id = message.from_user.id
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()

    cursor.execute("SELECT user1, user2 FROM active_chats WHERE user1 = ? OR user2 = ?", (user_id, user_id))
    chat = cursor.fetchone()
    
    if chat:
        companion_id = chat[1] if chat[0] == user_id else chat[0]
        
        # Обновляем статистику сообщений
        cursor.execute("UPDATE users SET msgs_sent = msgs_sent + 1 WHERE user_id = ?", (user_id,))
        cursor.execute("UPDATE users SET msgs_received = msgs_received + 1 WHERE user_id = ?", (companion_id,))
        conn.commit()
        conn.close()

        try:
            await message.copy_to(companion_id)
        except Exception:
            await message.answer("Не удалось доставить сообщение собеседнику.")
    else:
        conn.close()
        await message.answer("Вы не в чате. Нажмите «🔎 Найти собеседника».")


async def main():
    bot = Bot(token=TOKEN)
    logging.basicConfig(level=logging.INFO)
    print("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
