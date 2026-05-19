import sys
import os
import asyncio
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import ClientTimeout

from config import BOT_TOKEN, BOT_API_SERVER_URL, LOG_LEVEL
from database.models import init_db
from bot.handlers import router

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

storage = MemoryStorage()

LONG_TIMEOUT = ClientTimeout(total=3600, connect=30, sock_read=3600)


async def main():
    await init_db()

    if BOT_API_SERVER_URL:
        local_server = TelegramAPIServer.from_base(BOT_API_SERVER_URL)
        session = AiohttpSession(api=local_server, timeout=LONG_TIMEOUT)
        logging.info(f"Using local Bot API Server: {BOT_API_SERVER_URL}")
    else:
        session = AiohttpSession(timeout=LONG_TIMEOUT)

    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher(storage=storage)
    dp.include_router(router)

    logging.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
