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

from bot.database import (
    init_db,
    get_workers,
    add_worker,
    update_worker,
    set_worker_reserve,
    deactivate_worker,
    get_schedule_settings,
    set_schedule_settings,
    get_shift_for_week,


)


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


@app.post("/api/workers")
async def workers_add(data: dict):
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

    return await add_worker(name)


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

    worker = await update_worker(worker_id, name)

    if not worker:
        raise HTTPException(
            status_code=404,
            detail="Працівника не знайдено",
        )

    return worker


@app.delete("/api/workers/{worker_id}")
async def worker_delete(worker_id: int):
    worker = await deactivate_worker(worker_id)

    if not worker:
        raise HTTPException(
            status_code=404,
            detail="Працівника не знайдено",
        )

    return worker

@app.put("/api/workers/{worker_id}/reserve")
async def worker_reserve(worker_id: int, data: dict):
    is_reserve = bool(data.get("is_reserve", False))
    worker = await set_worker_reserve(worker_id, is_reserve)

    if not worker:
        raise HTTPException(
            status_code=404,
            detail="Працівника не знайдено",
        )

    return worker
@app.get("/api/schedule/shift")
async def schedule_shift(week_start: str):
    try:
        from datetime import date
        week_start = date.fromisoformat(week_start)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректна дата тижня")

    shift = await get_shift_for_week(week_start)

    if shift is None:
        raise HTTPException(status_code=404, detail="Налаштування зміни ще не задано")

    return {"week_start": week_start.isoformat(), "shift": shift}





# =========================
# Schedule Settings API
# =========================

@app.get("/api/schedule/settings")
async def schedule_settings_get():
    return await get_schedule_settings()


@app.put("/api/schedule/settings")
async def schedule_settings_update(data: dict):
    start_week = data.get("start_week")
    start_shift = data.get("start_shift")

    if not start_week:
        raise HTTPException(status_code=400, detail="Тиждень не вказано")

    try:
        start_shift = int(start_shift)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректна зміна")

    if start_shift not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="Зміна має бути 1, 2 або 3")

    try:
        from datetime import date
        start_week = date.fromisoformat(start_week)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректна дата тижня")

    return await set_schedule_settings(start_week, start_shift)

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
