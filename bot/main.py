import asyncio
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

dp = Dispatcher()


async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN не знайдено")

    bot = Bot(token=TOKEN)

    print("Бот запущений...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
