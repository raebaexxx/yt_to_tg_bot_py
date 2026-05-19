import logging
from aiogram import Bot

logger = logging.getLogger(__name__)


async def safe_edit_text(bot: Bot, chat_id: int, message_id: int, text: str):
    try:
        await bot.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
        )
    except Exception as e:
        logger.debug(f"Edit message failed (ignored): {e}")
