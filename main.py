import asyncio
import logging
import aiosqlite
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = "8376223950:AAE4GEMYTlBtVWz80cBuUyiblVZ9_wymFXo"
ADMIN_ID = 8859438543

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
                premium_expires TEXT,
                complaints INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                msgs_sent INTEGER DEFAULT 0,
                msgs_received INTEGER DEFAULT 0,
                stars_balance INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                user_id INTEGER PRIMARY KEY,
                target_gender TEXT
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

gender_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Парень"), KeyboardButton(text="Девушка")]
    ],
    resize_keyboard=True
)

search_preference_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔎 Любой"), KeyboardButton(text="👨 Парень"), KeyboardButton(text="👩 Девушка")]
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
                await message.answer(
                    "🚫 **Доступ ограничен**\n\n"
                    "<i>Вы заблокированы в этом боте за большое количество жалоб.</i>",
                    parse_mode="HTML"
                )
                return

        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
            exists = await cursor.fetchone()

    if not exists:
        await message.answer(
            "👋 **Добро пожаловать в анонимный чат!**\n\n"
            "<i>Давай заполним небольшую анкету. Как тебя зовут (или какой псевдоним)?</i>",
            parse_mode="HTML"
        )
        await state.set_state(RegisterState.waiting_for_name)
    else:
        await message.answer(
            "✨ **С возвращением!**\n\n"
            "<i>Выберите нужное действие в главном меню ниже 👇</i>",
            reply_markup=main_kb, parse_mode="HTML"
        )

@dp.message(RegisterState.waiting_for_name, F.text)
async def process_name(message: Message, state: FSMContext):
    if message.text.startswith("/"):
        return
    await state.update_data(name=message.text)
    await message.answer(
        "🎂 **Сколько тебе лет?**\n\n"
        "<i>Введите возраст цифрой (доступно от 16 лет):</i>",
        parse_mode="HTML"
    )
    await state.set_state(RegisterState.waiting_for_age)

@dp.message(RegisterState.waiting_for_age, F.text)
async def process_age(message: Message, state: FSMContext):
    if message.text.startswith("/"):
        return
    if message.text.isdigit():
        age = int(message.text)
        if age < 16:
            await message.answer(
                "⚠️ **Ограничение по возрасту**\n\n"
                "<i>Извините, бот предназначен только для пользователей от 16 лет.</i>",
                parse_mode="HTML"
            )
            return
    else:
        await message.answer("⚠️ Пожалуйста, введи возраст цифрами.")
        return
        
    await state.update_data(age=age)
    await message.answer(
        "🚻 **Укажите свой пол:**",
        reply_markup=gender_kb, parse_mode="HTML"
    )
    await state.set_state(RegisterState.waiting_for_gender)

@dp.message(RegisterState.waiting_for_gender, F.text)
async def process_gender(message: Message, state: FSMContext):
    if message.text not in ["Парень", "Девушка"]:
        await message.answer("⚠️ Пожалуйста, выберите пол с помощью кнопок ниже.")
        return

    gender = message.text
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
    await message.answer(
        "✅ **Регистрация успешно завершена!**\n\n"
        "<i>Добро пожаловать в систему. Приятного общения!</i>",
        reply_markup=main_kb, parse_mode="HTML"
    )

@dp.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("chat.db") as db:
        async with db.execute("SELECT is_premium, premium_expires FROM users WHERE user_id = ?", (user_id,)) as cursor:
            prem_data = await cursor.fetchone()
        if prem_data and prem_data[0] == 1 and prem_data[1]:
            if datetime.now() > datetime.fromisoformat(prem_data[1]):
                await db.execute("UPDATE users SET is_premium = 0, premium_expires = NULL WHERE user_id = ?", (user_id,))
                await db.commit()

        async with db.execute("SELECT name, age, gender, username, is_premium, premium_expires, complaints, msgs_sent, msgs_received, stars_balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()

    if not row:
        await message.answer("❌ Сначала пройдите регистрацию через команду /start")
        return

    name, age, gender, username, is_premium, expires, complaints, sent, received, stars = row
    status = f"👑 Премиум (до {expires[:10] if expires else 'навсегда'})" if is_premium else "⭐ Обычный"

    text = (
        f"👤 **Ваш профиль:**\n\n"
        f"🏷 **Имя:** {name}\n"
        f"🎂 **Возраст:** {age}\n"
        f"🚻 **Пол:** {gender}\n"
        f"🔗 **Юзернейм:** {'@' + username if username else 'Не указан'}\n"
        f"💎 **Статус:** {status}\n"
        f"⭐ **Баланс звёзд:** {stars} ⭐\n\n"
        f"📊 **Статистика:**\n"
        f"💬 Отправлено: {sent} | Получено: {received}\n"
        f"⚠️ Жалобы: {complaints} / 20"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "⭐ Купить Премиум")
async def buy_premium_menu(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 1 день — 75 XTR", callback_data="buy_prem_1")],
        [InlineKeyboardButton(text="⭐ 3 дня — 139 XTR", callback_data="buy_prem_3")],
        [InlineKeyboardButton(text="⭐ 7 дней — 289 XTR", callback_data="buy_prem_7")],
        [InlineKeyboardButton(text="⭐ 30 дней — 489 XTR", callback_data="buy_prem_30")]
    ])
    await message.answer(
        "💎 **Премиум-подписка**\n\n"
        "<i>Дает доступ к расширенным анкетным данным собеседника и возможности выбора пола при поиске!\n\nВыберите период подписки:</i>",
        reply_markup=kb, parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("buy_prem_"))
async def process_buy_prem(callback: types.CallbackQuery):
    days = int(callback.data.split("_")[2])
    
    prices_map = {
        1: (75, "Премиум на 1 день"),
        3: (139, "Премиум на 3 дня"),
        7: (289, "Премиум на 7 дней"),
        30: (489, "Премиум на 30 дней")
    }
    
    price, title = prices_map[days]
    prices = [LabeledPrice(label=title, amount=price)]
    
    await callback.message.answer_invoice(
        title=title,
        description=f"Активация VIP-статуса в анонимном чате на {days} дн.",
        payload=f"prem_{days}",
        currency="XTR",
        prices=prices,
        start_parameter="buy_prem"
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: types.PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    user_id = message.from_user.id
    payload = message.successful_payment.invoice_payload
    days = int(payload.split("_")[1])
    
    expires_at = datetime.now() + timedelta(days=days)
    
    async with aiosqlite.connect("chat.db") as db:
        await db.execute("""
            UPDATE users SET is_premium = 1, premium_expires = ?, stars_balance = stars_balance + 10 
            WHERE user_id = ?
        """, (expires_at.isoformat(), user_id))
        await db.commit()

    await message.answer(
        f"🎉 **Оплата прошла успешно!**\n\n"
        f"<i>Вам активирован Премиум-статус 👑 на {days} дн. и начислено +10 бонусных звёзд ⭐!</i>",
        parse_mode="HTML"
    )
    try:
        await message.bot.send_message(
            ADMIN_ID, 
            f"💰 **Успешная покупка!**\n\nПользователь ID `{user_id}` купил Премиум на {days} дней.", 
            parse_mode="Markdown"
        )
    except Exception:
        pass

@dp.message(F.text == "🔎 Найти собеседника")
async def search_companion_start(message: Message):
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
                await message.answer(
                    "⚠️ **Активный диалог**\n\n"
                    "<i>Вы уже находитесь в беседе! Сначала завершите текущий диалог.</i>",
                    parse_mode="HTML"
                )
                return

    if is_premium:
        await message.answer(
            "👥 **Настройка поиска**\n\n"
            "<i>Выберите, кого именно вы хотите найти:</i>",
            reply_markup=search_preference_kb, parse_mode="HTML"
        )
    else:
        await start_searching(message, "Любой")

@dp.message(F.text.in_(["🔎 Любой", "👨 Парень", "👩 Девушка"]))
async def process_search_preference(message: Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("chat.db") as db:
        async with db.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,)) as cursor:
            res = await cursor.fetchone()
    
    if not res or not res[0]:
        await message.answer(
            "🔒 **Доступно с Премиум**\n\n"
            "<i>Функция выбора пола собеседника доступна только для владельцев Премиум-статуса.</i>",
            reply_markup=main_kb, parse_mode="HTML"
        )
        return

    pref_map = {"🔎 Любой": "Любой", "👨 Парень": "Парень", "👩 Девушка": "Девушка"}
    target_gender = pref_map[message.text]
    await start_searching(message, target_gender)

async def start_searching(message: Message, target_gender: str):
    user_id = message.from_user.id
    async with aiosqlite.connect("chat.db") as db:
        async with db.execute("SELECT gender FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user_row = await cursor.fetchone()
        user_gender = user_row[0] if user_row else "Любой"

        if target_gender == "Любой":
            async with db.execute("SELECT user_id, gender FROM queue WHERE user_id != ?", (user_id,)) as cursor:
                companion = await cursor.fetchone()
        else:
            async with db.execute("""
                SELECT q.user_id, q.target_gender FROM queue q 
                JOIN users u ON q.user_id = u.user_id 
                WHERE q.user_id != ? AND u.gender = ? AND (q.target_gender = 'Любой' OR q.target_gender = ?)
            """, (user_id, target_gender, user_gender)) as cursor:
                companion = await cursor.fetchone()

        if companion:
            companion_id = companion[0]
            await db.execute("DELETE FROM queue WHERE user_id = ?", (companion_id,))
            await db.execute("INSERT INTO active_chats VALUES (?, ?)", (user_id, companion_id))
            await db.commit()
            
            connect_time = datetime.now().strftime("%H:%M")
            safety_warning = "🛡 <b>Правила безопасности:</b> не переходите в сторонние ЛС и не передавайте личные данные!\n\n"

            async def get_profile(target_id, viewer_prem):
                async with aiosqlite.connect("chat.db") as c:
                    async with c.execute("SELECT name, age, gender, username FROM users WHERE user_id = ?", (target_id,)) as cur:
                        res = await cur.fetchone()
                if not res: return "Анкета не найдена."
                c_name, c_age, c_gender, c_username = res
                if viewer_prem:
                    return f"📋 <b>Анкета собеседника:</b>\n• Имя: {c_name}\n• Возраст: {c_age}\n• Пол: {c_gender}\n• Юзернейм: @{c_username or 'нет'}\n• Время: {connect_time}"
                return "🔒 <i>Хотите видеть полную анкету? Оформите Премиум-подписку!</i>"

            async with db.execute("SELECT is_premium FROM users WHERE user_id = ?", (companion_id,)) as cur:
                comp_prem_row = await cur.fetchone()
            comp_prem = comp_prem_row[0] if comp_prem_row else 0

            async with db.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,)) as cur:
                user_prem_row = await cur.fetchone()
            user_prem = user_prem_row[0] if user_prem_row else 0

            p1 = await get_profile(companion_id, user_prem)
            p2 = await get_profile(user_id, comp_prem)

            await message.answer(f"🎉 <b>Собеседник найден!</b>\n\n{safety_warning}{p1}", reply_markup=main_kb, parse_mode="HTML")
            await message.bot.send_message(companion_id, f"🎉 <b>Собеседник найден!</b>\n\n{safety_warning}{p2}", reply_markup=main_kb, parse_mode="HTML")
        else:
            await db.execute("INSERT OR REPLACE INTO queue (user_id, target_gender) VALUES (?, ?)", (user_id, target_gender))
            await db.commit()
            await message.answer(
                "🔎 **Ищем собеседника...**\n\n"
                "<i>Мы подбираем для вас подходящего человека. Пожалуйста, ожидайте ⏳</i>",
                reply_markup=main_kb, parse_mode="HTML"
            )

@dp.message(F.text == "🎁 Подарить звёзды")
async def gift_stars_menu(message: Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("chat.db") as db:
        async with db.execute("SELECT user1, user2 FROM active_chats WHERE user1 = ? OR user2 = ?", (user_id, user_id)) as cursor:
            chat = await cursor.fetchone()

    if not chat:
        await message.answer(
            "❌ **Ошибка отправки подарка**\n\n"
            "<i>Вы не находитесь в активном диалоге с собеседником!</i>",
            parse_mode="HTML"
        )
        return

    companion_id = chat[1] if chat[0] == user_id else chat[0]

    gift_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Подарить 5 звёзд", callback_data=f"gift_5_{companion_id}"),
         InlineKeyboardButton(text="⭐ Подарить 10 звёзд", callback_data=f"gift_10_{companion_id}")]
    ])
    await message.answer(
        "🎁 **Система подарков**\n\n"
        "<i>Выберите количество звёзд для перевода собеседнику:</i>",
        reply_markup=gift_kb, parse_mode="HTML"
    )

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
            await callback.answer(f"❌ Недостаточно звёзд на балансе! У вас: {sender_balance} ⭐", show_alert=True)
            return

        await db.execute("UPDATE users SET stars_balance = stars_balance - ? WHERE user_id = ?", (amount, sender_id))
        await db.execute("UPDATE users SET stars_balance = stars_balance + ? WHERE user_id = ?", (amount, target_id))
        await db.commit()

    await callback.answer(f"🎁 Вы успешно подарили {amount} ⭐!", show_alert=True)
    await callback.message.edit_text(f"✅ **Подарок отправлен!**\n\n<i>Успешно передано: {amount} ⭐</i>", parse_mode="HTML")
    try:
        await callback.bot.send_message(
            target_id, 
            f"🎉 **Вам подарок!**\n\n<i>Собеседник перевел вам {amount} ⭐!</i>", 
            parse_mode="HTML"
        )
    except Exception:
        pass

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

            await message.answer(
                "🛑 **Диалог завершен**\n\n"
                "<i>Пожалуйста, оцените вашего собеседника:</i>",
                reply_markup=rating_kb, parse_mode="HTML"
            )
            try:
                await message.bot.send_message(
                    companion_id, 
                    "🛑 **Собеседник покинул чат**\n\n"
                    "<i>Пожалуйста, оцените общение с ним:</i>", 
                    reply_markup=rating_kb, parse_mode="HTML"
                )
            except Exception:
                pass
            
            await message.answer("🏠 Главное меню:", reply_markup=main_kb)
        try:
            await message.bot.send_message(companion_id, "🏠 Главное меню:", reply_markup=main_kb)
        except Exception:
            pass
        else:
                
            await message.answer(
                "⚠️ **Информация**\n\n"
                "<i>Вы сейчас ни с кем не общаетесь.</i>",
                reply_markup=main_kb, parse_mode="HTML"
            )

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
                await callback.bot.send_message(
                    target_id, 
                    "🚫 **Блокировка**\n\n"
                    "<i>Вы были заблокированы в боте за большое количество жалоб.</i>",
                    parse_mode="HTML"
                )
            except Exception:
                pass
        await db.commit()

    await callback.answer("⚠️ Жалоба успешно отправлена.", show_alert=True)
    await callback.message.edit_text("⚠️ **Жалоба принята.**\n\n<i>Спасибо за помощь в модерации.</i>", parse_mode="HTML")

@dp.callback_query(F.data.startswith("rate_"))
async def process_rating(callback: types.CallbackQuery):
    await callback.answer("Спасибо за вашу оценку!", show_alert=True)
    await callback.message.edit_text("✅ **Диалог полностью закрыт.**\n\n<i>Можете искать нового собеседника!</i>", parse_mode="HTML")

@dp.message()
async def forward_handler(message: Message):
    service_buttons = [
        "🔎 Найти собеседника", "👤 Профиль", "⭐ Купить Премиум", 
        "🎁 Подарить звёзды", "❌ Остановить диалог", "Парень", "Девушка",
        "🔎 Любой", "👨 Парень", "👩 Девушка"
    ]
    
    if message.text in service_buttons or (message.text and message.text.startswith("/")):
        return

    user_id = message.from_user.id
    async with aiosqlite.connect("chat.db") as db:
        async with db.execute("SELECT user1, user2 FROM active_chats WHERE user1 = ? OR user2 = ?", (user_id, user_id)) as cursor:
            chat = await cursor.fetchone()
        
        if chat:
            companion_id = chat[1] if chat[0] == user_id else chat[0]
            
            try:
                await message.send_copy(chat_id=companion_id)
                
                await db.execute("UPDATE users SET msgs_sent = msgs_sent + 1 WHERE user_id = ?", (user_id,))
                await db.execute("UPDATE users SET msgs_received = msgs_received + 1 WHERE user_id = ?", (companion_id,))
                await db.commit()
            except Exception:
                await message.answer("❌ Не удалось отправить сообщение собеседнику.")
        else:
            await message.answer(
                "⚠️ **Вы не в диалоге**\n\n"
                "<i>Нажмите кнопку «🔎 Найти собеседника», чтобы начать общение!</i>",
                reply_markup=main_kb, parse_mode="HTML"
            )

async def main():
    await init_db()
    logging.basicConfig(level=logging.INFO)
    print("Бот успешно запущен и готов к работе!")
    bot = Bot(token=TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
    

if __name__ == "__main__":
    asyncio.run(main())
