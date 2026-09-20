import asyncio
import logging
import sqlite3
from datetime import datetime
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
    # Таблица пользователей и анкет (добавлено поле stars_balance для подарков)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            age INTEGER,
            gender TEXT,
            username TEXT,
            is_premium INTEGER DEFAULT 0,
            complaints INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            msgs_sent INTEGER DEFAULT 0,
            msgs_received INTEGER DEFAULT 0,
            stars_balance INTEGER DEFAULT 0
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
        [KeyboardButton(text="🎁 Подарить звёзды"), KeyboardButton(text="❌ Остановить диалог")]
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
    username = message.from_user.username

    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (user_id, name, age, gender, username, is_premium, complaints, is_banned, msgs_sent, msgs_received, stars_balance)
        VALUES (?, ?, ?, ?, ?, 
            COALESCE((SELECT is_premium FROM users WHERE user_id = ?), 0),
            COALESCE((SELECT complaints FROM users WHERE user_id = ?), 0),
            COALESCE((SELECT is_banned FROM users WHERE user_id = ?), 0),
            COALESCE((SELECT msgs_sent FROM users WHERE user_id = ?), 0),
            COALESCE((SELECT msgs_received FROM users WHERE user_id = ?), 0),
            COALESCE((SELECT stars_balance FROM users WHERE user_id = ?), 0)
        )
    """, (user_id, name, age, gender, username, user_id, user_id, user_id, user_id, user_id, user_id))
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
    cursor.execute("SELECT name, age, gender, username, is_premium, complaints, msgs_sent, msgs_received, stars_balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await message.answer("Сначала пройдите регистрацию через /start")
        return

    name, age, gender, username, is_premium, complaints, sent, received, stars = row
    status = "👑 Премиум (VIP)" if is_premium else "⭐ Обычный"

    text = (
        f"👤 **Ваш профиль:**\n\n"
        f"🏷 Имя: {name if name else 'Не указано'}\n"
        f"🎂 Возраст: {age if age else 'Не указан'}\n"
        f"🚻 Пол: {gender if gender else 'Не указан'}\n"
        f"🔗 Юзернейм: {'@' + username if username else 'Не указан'}\n"
        f"💎 Статус: {status}\n"
        f"⭐ Баланс звёзд для подарков: {stars} ⭐\n\n"
        f"📊 **Статистика:**\n"
        f"💬 Отправлено сообщений: {sent}\n"
        f"📩 Получено сообщений: {received}\n"
        f"⚠️ Получено жалоб: {complaints} / 20"
    )
    await message.answer(text, parse_mode="Markdown")


# --- ПОКУПКА ПРЕМИУМА (TELEGRAM STARS - 45 ЗВЕЗД) ---
@dp.message(F.text == "⭐ Купить Премиум")
async def buy_premium(message: Message):
    prices = [LabeledPrice(label="VIP Премиум в анонимном чате", amount=45)]
    await message.answer_invoice(
        title="VIP Премиум-статус",
        description="Дает возможность видеть расширенные анкеты собеседников, юзернеймы и другие бонусы!",
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
    # Допустим, при покупке пакета пользователю также начисляются внутренние звезды на баланс (например, 10 звезд бонус)
    cursor.execute("UPDATE users SET is_premium = 1, stars_balance = stars_balance + 10 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    await message.answer("🎉 Успешно! Вам активирован Премиум-статус 👑 и начислено +10 бонусных звёзд на баланс подарков!")
    try:
        await message.bot.send_message(ADMIN_ID, f"💰 Пользователь ID {user_id} купил Премиум за 45 звёзд!")
    except Exception:
        pass


# --- СИСТЕМА ПОДАРКОВ И ПЕРЕВОДА ЗВЕЗД ---
@dp.message(F.text == "🎁 Подарить звёзды")
async def gift_stars_menu(message: Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user2 FROM active_chats WHERE user1 = ? OR user2 = ?", (user_id, user_id))
    chat = cursor.fetchone()
    conn.close()

    if not chat:
        await message.answer("❌ Вы сейчас не находитесь в активном диалоге с собеседником!\nЧтобы подарить звёзды, найдите собеседника через поиск.")
        return

    companion_id = chat[0] if chat != user_id else chat[1] # получаем ID собеседника

    gift_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Подарить 5 звёзд", callback_data=f"gift_5_{companion_id}"),
         InlineKeyboardButton(text="⭐ Подарить 10 звёзд", callback_data=f"gift_10_{companion_id}")]
    ])
    await message.answer("🎁 Выберите, сколько звёзд вы хотите подарить текущему собеседнику:", reply_markup=gift_kb)

@dp.callback_query(F.data.startswith("gift_"))
async def process_gift(callback: types.CallbackQuery):
    data_parts = callback.data.split("_")
    amount = int(data_parts[1])
    target_id = int(data_parts[2])
    sender_id = callback.from_user.id

    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()

    # Проверяем баланс отправителя
    cursor.execute("SELECT stars_balance FROM users WHERE user_id = ?", (sender_id,))
    res = cursor.fetchone()
    sender_balance = res[0] if res else 0

    if sender_balance < amount:
        conn.close()
        await callback.answer(f"❌ У вас недостаточно звёзд на балансе! Ваш баланс: {sender_balance} ⭐", show_alert=True)
        return

    # Переводим звезды
    cursor.execute("UPDATE users SET stars_balance = stars_balance - ? WHERE user_id = ?", (amount, sender_id))
    cursor.execute("UPDATE users SET stars_balance = stars_balance + ? WHERE user_id = ?", (amount, target_id))
    conn.commit()
    conn.close()

    await callback.answer(f"🎁 Вы успешно подарили {amount} ⭐ собеседнику!", show_alert=True)
    await callback.message.edit_text(f"✅ Подарок отправлен! Вы передали {amount} ⭐ собеседнику.")

    try:
        await callback.bot.send_message(target_id, f"🎉 Вам подарок! Собеседник перевел вам {amount} ⭐ на ваш баланс!")
    except Exception:
        pass


# --- ПОИСК СОБЕСЕДНИКА ---
@dp.message(F.text == "🔎 Найти собеседника")
async def search_companion(message: Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()

    cursor.execute("SELECT is_banned, is_premium FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()
    if user_info and user_info[0] == 1:
        conn.close()
        await message.answer("❌ Вы заблокированы.")
        return
    
    is_premium = user_info[1] if user_info else 0

    cursor.execute("SELECT * FROM active_chats WHERE user1 = ? OR user2 = ?", (user_id, user_id))
    if cursor.fetchone():
        await message.answer("Вы уже в чате! Завершите текущий диалог.")
        conn.close()
        return

    cursor.execute("SELECT user_id FROM queue WHERE user_id != ?", (user_id,))
    companion = cursor.fetchone()

    if companion:
        companion_id = companion[0]
        cursor.execute("DELETE FROM queue WHERE user_id = ?", (companion_id,))
        cursor.execute("INSERT INTO active_chats VALUES (?, ?)", (user_id, companion_id))
        conn.commit()
        conn.close()

        connect_time = datetime.now().strftime("%H:%M")
        safety_warning = (
            "🛡 <b>Внимание, безопасность превыше всего!</b>\n"
            "• <i>Не переходите в личные сообщения (ЛС) к незнакомцам.</i>\n"
            "• <i>Не отправляйте свои фото, видео и личные данные.</i>\n\n"
        )

        async def get_companion_profile(target_id, viewer_is_premium):
            c = sqlite3.connect("chat.db")
            cur = c.cursor()
            cur.execute("SELECT name, age, gender, username FROM users WHERE user_id = ?", (target_id,))
            res = cur.fetchone()
            c.close()
            if not res:
                return "Анкета не найдена."
            c_name, c_age, c_gender, c_username = res
            
            if viewer_is_premium:
                un_display = f"@{c_username}" if c_username else "Скрыт / Нет"
                return (
                    f"📋 <b>Расширенная анкета собеседника:</b>\n"
                    f"🏷 Имя: {c_name or 'Не указано'}\n"
                    f"🎂 Возраст: {c_age or 'Не указан'}\n"
                    f"🚻 Пол: {c_gender or 'Не указан'}\n"
                    f"🔗 Username: {un_display}\n"
                    f"⏱ Время соединения: {connect_time}"
                )
            else:
                return "🔒 <i>Хотите видеть полную анкету и юзернейм? Оформите Премиум за 45 звёзд!</i>"

        profile_for_user1 = await get_companion_profile(companion_id, is_premium)
        
        c2 = sqlite3.connect("chat.db")
        cur2 = c2.cursor()
        cur2.execute("SELECT is_premium FROM users WHERE user_id = ?", (companion_id,))
        comp_prem_row = cur2.fetchone()
        comp_prem = comp_prem_row[0] if comp_prem_row else 0
        c2.close()
        
        profile_for_user2 = await get_companion_profile(user_id, comp_prem)

        await message.answer(f"🎉 <b>Собеседник найден! Общайтесь.</b>\n\n{safety_warning}{profile_for_user1}", parse_mode="HTML")
        await message.bot.send_message(companion_id, f"🎉 <b>Собеседник найден! Общайтесь.</b>\n\n{safety_warning}{profile_for_user2}", parse_mode="HTML")
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
    
    cursor.execute("UPDATE users SET complaints = complaints + 1 WHERE user_id = ?", (target_id,))
    cursor.execute("SELECT complaints FROM users WHERE user_id = ?", (target_id,))
    res = cursor.fetchone()
    complaints_count = res[0] if res else 0

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
    if message.text in ["🔎 Найти собеседника", "👤 Профиль", "⭐ Купить Премиум", "🎁 Подарить звёзды", "❌ Остановить диалог"] or message.text and message.text.startswith("/"):
        return

    user_id = message.from_user.id
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()

    cursor.execute("SELECT user1, user2 FROM active_chats WHERE user1 = ? OR user2 = ?", (user_id, user_id))
    chat = cursor.fetchone()
    
    if chat:
        companion_id = chat[1] if chat[0] == user_id else chat[0]
        
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
