import sys
import os
import asyncio
import signal
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, BOT_API_SERVER_URL, LOG_LEVEL
from database.models import init_db, close_db
from bot.handlers import router

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

storage = MemoryStorage()

LONG_TIMEOUT = 3600.0


async def on_shutdown(bot: Bot):
    await close_db()
    await bot.session.close()
    logging.info("Bot stopped")


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

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    logging.info("Starting bot...")
    polling_task = asyncio.create_task(dp.start_polling(bot))

    await stop_event.wait()
    logging.info("Shutdown signal received...")

    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass

    await on_shutdown(bot)


if __name__ == "__main__":
    asyncio.run(main())
