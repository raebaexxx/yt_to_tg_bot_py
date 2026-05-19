import sys
import os
import asyncio
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, BOT_API_SERVER_URL, LOG_LEVEL
from database.models import init_db
from bot.handlers import router

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

storage = MemoryStorage()


async def main():
    await init_db()

    bot_settings = {"token": BOT_TOKEN}
    if BOT_API_SERVER_URL:
        bot_settings["api_server_url"] = BOT_API_SERVER_URL
        logging.info(f"Using local Bot API Server: {BOT_API_SERVER_URL}")

    bot = Bot(**bot_settings)
    dp = Dispatcher(storage=storage)
    dp.include_router(router)

    logging.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
