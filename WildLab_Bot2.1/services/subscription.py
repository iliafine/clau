from aiogram import Bot
from config import Config
import logging

logger = logging.getLogger(__name__)

async def check_subscription(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(Config.CHANNEL_ID, user_id)
        return member.status in {"member", "administrator", "creator"}
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return False