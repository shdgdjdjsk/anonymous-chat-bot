import os
import sqlite3
import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(TOKEN)
dp = Dispatcher()

DB = "bot.db"

waiting = None
pairs = {}


def db():
    return sqlite3.connect(DB)


def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            gender TEXT,
            search_gender TEXT
        )
    """)

    con.commit()
    con.close()


def add_user(user_id):
    con = db()
    cur = con.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (user_id,)
    )
    con.commit()
    con.close()


def menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔎 Найти собеседника",
                    callback_data="search"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➡️ Следующий",
                    callback_data="next"
                ),
                InlineKeyboardButton(
                    text="❌ Завершить",
                    callback_data="stop"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Premium",
                    callback_data="premium"
                )
            ]
        ]
    )


@dp.message(CommandStart())
async def start(message: Message):
    add_user(message.from_user.id)

    await message.answer(
        "👋 Добро пожаловать в анонимный чат!\n\n"
        "Здесь ты можешь случайно познакомиться "
        "с другим человеком.\n\n"
        "Нажми «Найти собеседника», чтобы начать.",
        reply_markup=menu()
    )


async def find_partner(user_id):
    global waiting

    if waiting is None:
        waiting = user_id

        await bot.send_message(
            user_id,
            "🔎 Ищу собеседника..."
        )
        return

    if waiting == user_id:
        return

    partner = waiting
    waiting = None

    pairs[user_id] = partner
    pairs[partner] = user_id

    await bot.send_message(
        user_id,
        "💬 Собеседник найден!\n\n"
        "Можете начинать общение."
    )

    await bot.send_message(
        partner,
        "💬 Собеседник найден!\n\n"
        "Можете начинать общение."
    )


@dp.callback_query(F.data == "search")
async def search(callback: CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id

    if user_id in pairs:
        await callback.message.answer(
            "❗ Ты уже общаешься с собеседником."
        )
        return

    await find_partner(user_id)


@dp.callback_query(F.data == "next")
async def next_partner(callback: CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id

    if user_id in pairs:
        partner = pairs[user_id]

        del pairs[user_id]

        if partner in pairs:
            del pairs[partner]

        await bot.send_message(
            partner,
            "❌ Собеседник завершил разговор.",
            reply_markup=menu()
        )

    await find_partner(user_id)


@dp.callback_query(F.data == "stop")
async def stop(callback: CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id

    if user_id in pairs:
        partner = pairs[user_id]

        del pairs[user_id]

        if partner in pairs:
            del pairs[partner]

        await bot.send_message(
            partner,
            "❌ Собеседник завершил разговор.",
            reply_markup=menu()
        )

        await callback.message.answer(
            "Разговор завершён.",
            reply_markup=menu()
        )

    else:
        await callback.message.answer(
            "Ты сейчас ни с кем не общаешься.",
            reply_markup=menu()
        )


@dp.callback_query(F.data == "premium")
async def premium(callback: CallbackQuery):
    await callback.answer()

    await callback.message.answer(
        "⭐ PREMIUM\n\n"
        "В Premium можно будет добавить:\n\n"
        "🔎 Приоритетный поиск\n"
        "👤 Фильтр по полу\n"
        "🎯 Интересы\n"
        "✨ Дополнительные функции\n\n"
        "Скоро здесь появится покупка за Telegram Stars."
    )


@dp.message()
async def messages(message: Message):
    user_id = message.from_user.id

    if user_id not in pairs:
        return

    partner = pairs[user_id]

    try:
        await message.copy_to(partner)
    except Exception:
        pass


async def main():
    init_db()

    print("BOT STARTED")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
