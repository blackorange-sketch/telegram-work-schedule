import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    Message,
)

from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import uvicorn

from bot.database import init_db, get_workers, update_worker


load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL")

dp = Dispatcher()
app = FastAPI()


# =========================
# Mini App
# =========================

app.mount(
    "/static",
    StaticFiles(directory="web/static"),
    name="static",
)


@app.get("/")
async def index():
    return FileResponse("web/index.html")


# =========================
# Workers API
# =========================

@app.get("/api/workers")
async def workers_list():
    return await get_workers()


@app.put("/api/workers/{worker_id}")
async def worker_update(worker_id: int, data: dict):
    name = str(data.get("name", "")).strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Ім'я не може бути порожнім",
        )

    if len(name) > 100:
        raise HTTPException(
            status_code=400,
            detail="Ім'я занадто довге",
        )

    workers = await get_workers()

    if not any(worker["id"] == worker_id for worker in workers):
        raise HTTPException(
            status_code=404,
            detail="Працівника не знайдено",
        )

    await update_worker(worker_id, name)

    return {
        "success": True,
        "id": worker_id,
        "name": name,
    }


# =========================
# Telegram Bot
# =========================

@dp.message(CommandStart())
async def start_handler(message: Message):
    if not WEB_APP_URL:
        await message.answer(
            "Mini App ще не налаштований.\n"
            "Додай WEB_APP_URL у змінні Railway."
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Відкрити розклад",
                    web_app=WebAppInfo(url=WEB_APP_URL),
                )
            ]
        ]
    )

    await message.answer(
        "👋 Вітаю!\n\n"
        "Це система робочого розкладу.\n"
        "Натисни кнопку нижче, щоб відкрити Mini App.",
        reply_markup=keyboard,
    )


# =========================
# Bot
# =========================

async def run_bot():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN не знайдено")

    bot = Bot(token=TOKEN)

    await bot.set_my_commands(
        [
            BotCommand(
                command="start",
                description="Відкрити розклад",
            )
        ]
    )

    print("Telegram bot запускається...")

    await dp.start_polling(bot)


# =========================
# Web server
# =========================

async def run_web():
    port = int(os.getenv("PORT", "8080"))

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )

    server = uvicorn.Server(config)

    print(f"Web server запускається на порту {port}")

    await server.serve()


# =========================
# Main
# =========================

async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN не знайдено")

    print("Підключення до PostgreSQL...")

    await init_db()

    print("PostgreSQL підключено.")

    await asyncio.gather(
        run_bot(),
        run_web(),
    )


if __name__ == "__main__":
    asyncio.run(main())
