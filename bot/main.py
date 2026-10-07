import asyncio
import hashlib
import hmac
import json
import time
import os
import tempfile
import uuid
import urllib.parse
import urllib.request

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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
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
    get_or_create_schedule_week,
    create_schedule_days,
    update_schedule_day,
    get_schedule_assignments,
    get_schedule_reserves,
    set_schedule_reserve,
    delete_schedule_reserve,
    generate_schedule_assignments,
    set_schedule_assignment,
    delete_schedule_assignment,
    delete_schedule_assignments_for_week,
    get_worker_days_off,
    set_worker_day_off,
    delete_worker_day_off,
    get_lunch_settings,
    set_lunch_setting,


)


load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL")
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

# Telegram не оновлює initData, поки Mini App відкритий (навіть у фоні),
# тому 1 години замало: після довгого згортання всі запити повертали б 403.
INIT_DATA_MAX_AGE_SECONDS = 24 * 60 * 60

def validate_telegram_init_data(init_data):
    if not TOKEN or not init_data:
        return None

    from urllib.parse import parse_qsl

    data = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = data.pop("hash", None)

    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(data.items())
    )

    secret_key = hmac.new(
        b"WebAppData",
        TOKEN.encode(),
        hashlib.sha256,
    ).digest()

    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        return None

    try:
        auth_date = int(data.get("auth_date", "0"))
        if not auth_date or time.time() - auth_date > INIT_DATA_MAX_AGE_SECONDS:
            return None

        user = json.loads(data["user"])
        return user
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def require_admin(request: Request):
    init_data = request.headers.get("X-Telegram-Init-Data")
    user = validate_telegram_init_data(init_data)
    if not user or user.get("id") not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Доступ дозволено лише адміністраторам")
    return user


dp = Dispatcher()
app = FastAPI()

@app.middleware("http")
async def admin_api_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path not in {"/api/auth/me"} and not request.url.path.startswith("/api/export/schedule/"):
        try:
            require_admin(request)
        except HTTPException as error:
            # HTTPException, піднятий у middleware, не обробляється FastAPI
            # і перетворюється на 500, тому повертаємо відповідь явно.
            return JSONResponse(
                status_code=error.status_code,
                content={"detail": error.detail},
            )

    return await call_next(request)


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

@app.get("/api/auth/me")
async def auth_me(request: Request):
    user = require_admin(request)
    return {"authorized": True, "user_id": user["id"]}


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

@app.put("/api/lunch/settings")
async def lunch_settings_update(data: dict):
    try:
        from datetime import date, time

        week_start = date.fromisoformat(data.get("week_start"))
        shift = int(data.get("shift"))
        pair_number = int(data.get("pair_number"))

        worker1_id = data.get("worker1_id")
        worker2_id = data.get("worker2_id")

        if worker1_id is not None:
            worker1_id = int(worker1_id)

        if worker2_id is not None:
            worker2_id = int(worker2_id)

        start_time = time.fromisoformat(data.get("start_time"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректні дані обіду")

    if shift not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="Некоректна зміна")

    if pair_number not in range(1, 6):
        raise HTTPException(status_code=400, detail="Некоректний номер пари")

    week = await get_or_create_schedule_week(week_start)

    return await set_lunch_setting(
        week["id"],
        shift,
        pair_number,
        worker1_id,
        worker2_id,
        start_time,
    )


@app.get("/api/lunch/settings")
async def lunch_settings_get(week_start: str):
    try:
        from datetime import date
        week_start = date.fromisoformat(week_start)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректна дата тижня")

    week = await get_or_create_schedule_week(week_start)
    return await get_lunch_settings(week["id"])


@app.get("/api/schedule/assignments")
async def schedule_assignments_get(week_start: str):
    try:
        from datetime import date
        week_start = date.fromisoformat(week_start)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректна дата тижня")

    week = await get_or_create_schedule_week(week_start)
    assignments = await get_schedule_assignments(week["id"])
    reserves = await get_schedule_reserves(week["id"])

    return {
        "week": week,
        "assignments": assignments,
        "reserves": reserves
    }


@app.put("/api/schedule/assignment")
async def schedule_assignment_update(data: dict):
    try:
        from datetime import date

        week_start = date.fromisoformat(data.get("week_start"))
        work_date = date.fromisoformat(data.get("work_date"))
        worker_id = int(data.get("worker_id"))
        station = int(data.get("station"))
        shift = int(data.get("shift"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректні дані призначення")

    if station not in range(15, 25):
        raise HTTPException(status_code=400, detail="Некоректна станція")

    if shift not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="Некоректна зміна")

    week = await get_or_create_schedule_week(week_start)

    assignment = await set_schedule_assignment(
        week["id"],
        work_date,
        worker_id,
        station,
        shift,
    )

    if assignment is None:
        raise HTTPException(
            status_code=404,
            detail="Призначення не знайдено",
        )

    return assignment


@app.delete("/api/schedule/assignment")
async def schedule_assignment_delete(data: dict):
    try:
        from datetime import date

        week_start = date.fromisoformat(data.get("week_start"))
        work_date = date.fromisoformat(data.get("work_date"))
        station = int(data.get("station"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректні дані призначення")

    if station not in range(15, 25):
        raise HTTPException(status_code=400, detail="Некоректна станція")

    week = await get_or_create_schedule_week(week_start)

    assignment = await delete_schedule_assignment(
        week["id"],
        work_date,
        station,
    )

    if assignment is None:
        raise HTTPException(
            status_code=404,
            detail="Призначення не знайдено",
        )

    return {"deleted": True, "assignment": assignment}


@app.put("/api/schedule/reserve")
async def schedule_reserve_put(data: dict):
    from datetime import date

    try:
        week_start = date.fromisoformat(data["week_start"])
        work_date = date.fromisoformat(data["work_date"])
        worker_id = int(data["worker_id"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректні дані Reserve")

    week = await get_or_create_schedule_week(week_start)
    await set_schedule_reserve(week["id"], work_date, worker_id)

    return {"ok": True}


@app.delete("/api/schedule/reserve")
async def schedule_reserve_delete(
    week_start: str,
    work_date: str,
    worker_id: int,
):
    from datetime import date

    try:
        week_start = date.fromisoformat(week_start)
        work_date = date.fromisoformat(work_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Некоректна дата")

    week = await get_or_create_schedule_week(week_start)
    await delete_schedule_reserve(week["id"], work_date, worker_id)

    return {"ok": True}


@app.post("/api/schedule/generate")
async def schedule_generate(data: dict):
    try:
        from datetime import date
        week_start = date.fromisoformat(data.get("week_start"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректна дата тижня")

    shift = await get_shift_for_week(week_start)

    if shift is None:
        raise HTTPException(
            status_code=400,
            detail="Спочатку потрібно налаштувати початкову зміну"
        )

    week = await get_or_create_schedule_week(week_start)

    await delete_schedule_assignments_for_week(week["id"])

    generated = await generate_schedule_assignments(
        week["id"],
        week_start,
        shift
    )

    assignments = await get_schedule_assignments(week["id"])

    return {
        "week": week,
        "shift": shift,
        "generated": generated,
        "assignments": assignments
    }


@app.get("/api/schedule/days")
async def schedule_days_get(week_start: str):
    try:
        from datetime import date
        week_start = date.fromisoformat(week_start)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректна дата тижня")

    week = await get_or_create_schedule_week(week_start)
    days = await create_schedule_days(week["id"], week_start)

    return {
        "week": week,
        "days": days
    }



@app.get("/api/worker-days-off")
async def worker_days_off_get(start_date: str, end_date: str):
    try:
        from datetime import date
        start_date = date.fromisoformat(start_date)
        end_date = date.fromisoformat(end_date)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректні дати")

    if start_date > end_date:
        raise HTTPException(status_code=400, detail="Некоректний діапазон дат")

    days_off = await get_worker_days_off(start_date, end_date)

    return {
        "days_off": days_off
    }


@app.put("/api/worker-days-off")
async def worker_days_off_update(data: dict):
    try:
        from datetime import date
        worker_id = int(data.get("worker_id"))
        work_date = date.fromisoformat(data.get("work_date"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректні дані")

    is_day_off = bool(data.get("is_day_off", True))

    if is_day_off:
        result = await set_worker_day_off(worker_id, work_date)
    else:
        result = await delete_worker_day_off(worker_id, work_date)

    return {
        "day_off": result
    }


@app.delete("/api/worker-days-off")
async def worker_days_off_delete(worker_id: int, work_date: str):
    try:
        from datetime import date
        work_date = date.fromisoformat(work_date)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректна дата")

    result = await delete_worker_day_off(worker_id, work_date)

    if result is None:
        raise HTTPException(status_code=404, detail="Вихідний не знайдено")

    return {
        "deleted": True,
        "day_off": result
    }


@app.put("/api/schedule/days")
async def schedule_day_update(data: dict):
    try:
        from datetime import date
        week_start = date.fromisoformat(data.get("week_start"))
        work_date = date.fromisoformat(data.get("work_date"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректна дата")

    is_working_day = bool(data.get("is_working_day", True))
    default_shift = data.get("default_shift")

    if default_shift is not None:
        try:
            default_shift = int(default_shift)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Некоректна зміна")

        if default_shift not in (1, 2, 3):
            raise HTTPException(status_code=400, detail="Зміна має бути 1, 2 або 3")

    week = await get_or_create_schedule_week(week_start)
    day = await update_schedule_day(
        week["id"],
        work_date,
        is_working_day,
        default_shift
    )

    if not day:
        raise HTTPException(status_code=404, detail="День розкладу не знайдено")

    return day



@app.post("/api/export/schedule")
async def export_schedule(request: Request):
    data = await request.body()

    if not data:
        raise HTTPException(status_code=400, detail="Порожній файл")

    if not data.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=400, detail="Очікується JPEG")

    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл завеликий")

    file_id = uuid.uuid4().hex
    file_path = os.path.join(tempfile.gettempdir(), f"schedule-{file_id}.jpg")

    with open(file_path, "wb") as file:
        file.write(data)

    return {
        "file_id": file_id,
        "url": f"/api/export/schedule/{file_id}"
    }


@app.get("/api/export/schedule/{file_id}")
async def download_schedule(file_id: str):
    if not file_id.isalnum():
        raise HTTPException(status_code=400, detail="Некоректний файл")

    file_path = os.path.join(tempfile.gettempdir(), f"schedule-{file_id}.jpg")

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Файл не знайдено")

    return FileResponse(
        file_path,
        media_type="image/jpeg",
        filename="schedule.jpg"
    )


@app.post("/api/export/share-prepared")
async def share_prepared_schedule(request: Request):
    init_data = request.headers.get("X-Telegram-Init-Data")
    user = validate_telegram_init_data(init_data)

    if not user:
        raise HTTPException(status_code=401, detail="Некоректні дані Telegram")

    data = await request.body()

    if not data.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=400, detail="Очікується JPEG")

    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="JPEG завеликий для Telegram")

    if not WEB_APP_URL:
        raise HTTPException(status_code=500, detail="WEB_APP_URL не налаштований")

    file_id = uuid.uuid4().hex
    file_path = os.path.join(tempfile.gettempdir(), f"schedule-{file_id}.jpg")

    with open(file_path, "wb") as file:
        file.write(data)

    photo_url = f"{WEB_APP_URL.rstrip('/')}/api/export/schedule/{file_id}"

    result = {
        "type": "photo",
        "id": file_id,
        "photo_url": photo_url,
        "thumbnail_url": photo_url,
        "caption": "📅 Schedule",
    }

    payload = urllib.parse.urlencode({
        "user_id": str(user["id"]),
        "result": json.dumps(result, ensure_ascii=False),
        "allow_user_chats": "true",
        "allow_group_chats": "true",
        "allow_channel_chats": "true",
    }).encode()

    bot_api_url = f"https://api.telegram.org/bot{TOKEN}/savePreparedInlineMessage"

    response_data = None
    last_error = None

    for attempt, delay in enumerate((0, 0.3, 0.8), start=1):
        if delay:
            await asyncio.sleep(delay)

        started_at = time.monotonic()
        print(f"SHARE PREPARED attempt={attempt} started")

        try:
            request_obj = urllib.request.Request(
                bot_api_url,
                data=payload,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            with urllib.request.urlopen(request_obj, timeout=15) as response:
                response_data = json.loads(response.read().decode())

            elapsed = time.monotonic() - started_at
            print(
                f"SHARE PREPARED attempt={attempt} "
                f"elapsed={elapsed:.3f}s "
                f"ok={response_data.get('ok')}"
            )

            if response_data.get("ok"):
                break

            last_error = response_data.get(
                "description",
                "Telegram API error",
            )

        except Exception as error:
            elapsed = time.monotonic() - started_at
            last_error = str(error)
            print(
                f"SHARE PREPARED attempt={attempt} "
                f"elapsed={elapsed:.3f}s "
                f"error={last_error}"
            )

    if not response_data or not response_data.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=f"Помилка Telegram API: {last_error}",
        )

    if not response_data.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=response_data.get("description", "Telegram API error"),
        )

    prepared = response_data.get("result")

    if not prepared or not prepared.get("id"):
        raise HTTPException(
            status_code=502,
            detail="Telegram не повернув prepared message",
        )

    return {
        "prepared_message_id": prepared["id"]
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
