import asyncio
import logging
import aiosqlite
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice,
    ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = "8376223950:AAE4GEMYTlBtVWz80cBuUyiblVZ9_wymFXo"
ADMIN_ID = 8859438543

# --- АСИНХРОННАЯ БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect("chat.db") as db:
        await db.execute("""
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                user_id INTEGER PRIMARY KEY
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS active_chats (
                user1 INTEGER,
                user2 INTEGER
            )
        """)
        await db.commit()

class RegisterState(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_gender = State()

dp = Dispatcher(storage=MemoryStorage())

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
    
    async with aiosqlite.connect("chat.db") as db:
        async with db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] == 1:
                await message.answer("❌ Вы заблокированы в этом боте за большое количество жалоб.")
                return

        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
            exists = await cursor.fetchone()

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
    if message.text != "⏭ Пропустить":
        if message.text.isdigit():
            age = int(message.text)
            if age < 16:
                await message.answer("⚠️ Извините, бот предназначен для пользователей от 16 лет.")
                return
        else:
            await message.answer("Пожалуйста, введи возраст цифрами или нажми «Пропустить».")
            return
    else:
        age = None
        
    await state.update_data(age=age)
    await message.answer("Укажи свой пол:", reply_markup=gender_kb)
    await state.set_state(RegisterState.waiting_for_gender)

@dp.message(RegisterState.waiting_for_gender, F.text)
async def process_gender(message: Message, state: FSMContext):
    if message.text not in ["Мат.", "Жен.", "⏭ Пропустить"]:
        await message.answer("Пожалуйста, выберите пол с помощью кнопок ниже.")
        return

    gender = None if message.text == "⏭ Пропустить" else message.text
    data = await state.get_data()
    
    user_id = message.from_user.id
    username = message.from_user.username

    async with aiosqlite.connect("chat.db") as db:
        await db.execute("""
            INSERT INTO users (user_id, name, age, gender, username, stars_balance)
            VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                age = excluded.age,
                gender = excluded.gender,
                username = excluded.username
        """, (user_id, data.get("name"), data.get("age"), gender, username))
        await db.commit()

    await state.clear()
    await message.answer("✅ Регистрация завершена! Добро пожаловать.", reply_markup=main_kb)

@dp.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("chat.db") as db:
        async with db.execute("SELECT name, age, gender, username, is_premium, complaints, msgs_sent, msgs_received, stars_balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()

    if not row:
        await message.answer("Сначала пройдите регистрацию через /start")
        return

    name, age, gender, username, is_premium, complaints, sent, received, stars = row
    status = "👑 Премиум (VIP)" if is_premium else "⭐ Обычный"

    text = (
        f"👤 **Ваш профиль:**\n\n"
        f"🏷 Имя: {name or 'Не указано'}\n"
        f"🎂 Возраст: {age or 'Не указан'}\n"
        f"🚻 Пол: {gender or 'Не указан'}\n"
        f"🔗 Юзернейм: {'@' + username if username else 'Не указан'}\n"
        f"💎 Статус: {status}\n"
        f"⭐ Баланс звёзд для подарков: {stars} ⭐\n\n"
        f"📊 **Статистика:**\n"
        f"💬 Отправлено сообщений: {sent}\n"
        f"📩 Получено сообщений: {received}\n"
        f"⚠️ Получено жалоб: {complaints} / 20"
    )
    await message.answer(text, parse_mode="Markdown")

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
    async with aiosqlite.connect("chat.db") as db:
        await db.execute("UPDATE users SET is_premium = 1, stars_balance = stars_balance + 10 WHERE user_id = ?", (user_id,))
        await db.commit()

    await message.answer("🎉 Успешно! Вам активирован Премиум-статус 👑 и начислено +10 бонусных звёзд!")
    try:
        await message.bot.send_message(ADMIN_ID, f"💰 Пользователь ID {user_id} купил Премиум за 45 звёзд!")
    except Exception:
        pass

@dp.message(F.text == "🎁 Подарить звёзды")
async def gift_stars_menu(message: Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("chat.db") as db:
        async with db.execute("SELECT user1, user2 FROM active_chats WHERE user1 = ? OR user2 = ?", (user_id, user_id)) as cursor:
            chat = await cursor.fetchone()

    if not chat:
        await message.answer("❌ Вы не в активном диалоге с собеседником!")
        return

    companion_id = chat[1] if chat[0] == user_id else chat[0]

    gift_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Подарить 5 звёзд", callback_data=f"gift_5_{companion_id}"),
         InlineKeyboardButton(text="⭐ Подарить 10 звёзд", callback_data=f"gift_10_{companion_id}")]
    ])
    await message.answer("🎁 Выберите, сколько звёзд подарить собеседнику:", reply_markup=gift_kb)

@dp.callback_query(F.data.startswith("gift_"))
async def process_gift(callback: types.CallbackQuery):
    data_parts = callback.data.split("_")
    amount = int(data_parts[1])
    target_id = int(data_parts[2])
    sender_id = callback.from_user.id

    async with aiosqlite.connect("chat.db") as db:
        async with db.execute("SELECT stars_balance FROM users WHERE user_id = ?", (sender_id,)) as cursor:
            res = await cursor.fetchone()
        sender_balance = res[0] if res else 0

        if sender_balance < amount:
            await callback.answer(f"❌ Недостаточно звёзд! Баланс: {sender_balance} ⭐", show_alert=True)
            return

        await db.execute("UPDATE users SET stars_balance = stars_balance - ? WHERE user_id = ?", (amount, sender_id))
        await db.execute("UPDATE users SET stars_balance = stars_balance + ? WHERE user_id = ?", (amount, target_id))
        await db.commit()

    await callback.answer(f"🎁 Вы подарили {amount} ⭐!", show_alert=True)
    await callback.message.edit_text(f"✅ Подарок отправлен! Передано {amount} ⭐.")
    try:
        await callback.bot.send_message(target_id, f"🎉 Вам подарок! Собеседник перевел вам {amount} ⭐!")
    except Exception:
        pass

@dp.message(F.text == "🔎 Найти собеседника")
async def search_companion(message: Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("chat.db") as db:
        async with db.execute("SELECT is_banned, is_premium FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user_info = await cursor.fetchone()
        if user_info and user_info[0] == 1:
            await message.answer("❌ Вы заблокированы.")
            return
        is_premium = user_info[1] if user_info else 0

        async with db.execute("SELECT * FROM active_chats WHERE user1 = ? OR user2 = ?", (user_id, user_id)) as cursor:
            if await cursor.fetchone():
                await message.answer("Вы уже в чате! Завершите текущий диалог.")
                return

        async with db.execute("SELECT user_id FROM queue WHERE user_id != ?", (user_id,)) as cursor:
            companion = await cursor.fetchone()

        if companion:
            companion_id = companion[0]
            await db.execute("DELETE FROM queue WHERE user_id = ?", (companion_id,))
            await db.execute("INSERT INTO active_chats VALUES (?, ?)", (user_id, companion_id))
            await db.commit()
            
            connect_time = datetime.now().strftime("%H:%M")
            safety_warning = "🛡 <b>Внимание: не переходите в ЛС и не отправляйте личные данные!</b>\n\n"

            async def get_profile(target_id, viewer_prem):
                async with aiosqlite.connect("chat.db") as c:
                    async with c.execute("SELECT name, age, gender, username FROM users WHERE user_id = ?", (target_id,)) as cur:
                        res = await cur.fetchone()
                if not res: return "Анкета не найдена."
                c_name, c_age, c_gender, c_username = res
                if viewer_prem:
                    return f"📋 <b>Анкета:</b>\nИмя: {c_name or '-'}\nВозраст: {c_age or '-'}\nПол: {c_gender or '-'}\nЮзернейм: @{c_username or 'нет'}\nВремя: {connect_time}"
                return "🔒 <i>Хотите видеть полную анкету? Оформите Премиум за 45 звёзд!</i>"

            p1 = await get_profile(companion_id, is_premium)
            
            async with aiosqlite.connect("chat.db") as c2:
                async with c2.execute("SELECT is_premium FROM users WHERE user_id = ?", (companion_id,)) as cur2:
                    cp_row = await cur2.fetchone()
            cp_prem = cp_row[0] if cp_row else 0
            p2 = await get_profile(user_id, cp_prem)

            await message.answer(f"🎉 <b>Собеседник найден!</b>\n\n{safety_warning}{p1}", parse_mode="HTML")
            await message.bot.send_message(companion_id, f"🎉 <b>Собеседник найден!</b>\n\n{safety_warning}{p2}", parse_mode="HTML")
        else:
            await db.execute("INSERT OR IGNORE INTO queue VALUES (?)", (user_id,))
            await db.commit()
            await message.answer("Ищем собеседника... Ожидайте ⏳")

@dp.message(F.text == "❌ Остановить диалог")
async def stop_chat(message: Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("chat.db") as db:
        await db.execute("DELETE FROM queue WHERE user_id = ?", (user_id,))
        async with db.execute("SELECT user1, user2 FROM active_chats WHERE user1 = ? OR user2 = ?", (user_id, user_id)) as cursor:
            chat = await cursor.fetchone()

        if chat:
            companion_id = chat[1] if chat[0] == user_id else chat[0]
            await db.execute("DELETE FROM active_chats WHERE user1 = ? OR user2 = ?", (user_id, user_id))
            await db.commit()

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
            await message.answer("Вы сейчас ни с кем не общаетесь.", reply_markup=main_kb)

@dp.callback_query(F.data.startswith("complaint_"))
async def process_complaint(callback: types.CallbackQuery):
    target_id = int(callback.data.split("_")[1])
    async with aiosqlite.connect("chat.db") as db:
        await db.execute("UPDATE users SET complaints = complaints + 1 WHERE user_id = ?", (target_id,))
        async with db.execute("SELECT complaints FROM users WHERE user_id = ?", (target_id,)) as cursor:
            res = await cursor.fetchone()
        complaints_count = res[0] if res else 0

        if complaints_count >= 20:
            await db.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (target_id,))
            try:
                await callback.bot.send_message(target_id, "❌ Вы заблокированы за жалобы.")
            except Exception:
                pass
        await db.commit()

    await callback.answer("⚠️ Жалоба отправлена.", show_alert=True)
    await callback.message.edit_text("⚠️ Жалоба принята.")

@dp.callback_query(F.data.startswith("rate_"))
async def process_rating(callback: types.CallbackQuery):
    await callback.answer("Спасибо за оценку!", show_alert=True)
    await callback.message.edit_text("✅ Диалог закрыт.")

@dp.message()
async def forward_handler(message: Message):
    service_buttons = [
        "🔎 Найти собеседника", "👤 Профиль", "⭐ Купить Премиум", 
        "🎁 Подарить звёзды", "❌ Остановить диалог", "⏭ Пропустить",
        "Мат.", "Жен."
    ]
    
    if message.text in service_buttons or (message.text and message.text.startswith("/")):
        return

    user_id = message.from_user.id
    async with aiosqlite.connect("chat.db") as db:
        async with db.execute("SELECT user1, user2 FROM active_chats WHERE user1 = ? OR user2 = ?", (user_id, user_id)) as cursor:
            chat = await cursor.fetchone()
        
        if chat:
            companion_id = chat[1] if chat[0] == user_id else chat[0]
            await db.execute("UPDATE users SET msgs_sent = msgs_sent + 1 WHERE user_id = ?", (user_id,))
            await db.execute("UPDATE users SET msgs_received = msgs_received + 1 WHERE user_id = ?", (companion_id,))
            await db.commit()

            try:
                await message.copy_to(companion_id)
            except Exception:
                await message.answer("Не удалось доставить сообщение.")
        else:
            await message.answer("Вы не в чате. Нажмите «🔎 Найти собеседника».", reply_markup=main_kb)

async def main():
    await init_db()
    bot = Bot(token=TOKEN)
    logging.basicConfig(level=logging.INFO)
    print("Асинхронный бот успешно запущен и работает без лагов!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
        
