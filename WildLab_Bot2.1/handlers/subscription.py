from aiogram import Router, types, Bot
from services.subscription import check_subscription
from keyboards import tables_menu, subscription_menu
import logging

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(lambda c: c.data == "check_subscription")
async def check_subscription_handler(callback: types.CallbackQuery, bot: Bot):
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Delete error: {e}")

    if await check_subscription(bot, callback.from_user.id):
        await callback.message.answer(
            "📊 Выберите таблицу:",
            reply_markup=tables_menu(),
            parse_mode="Markdown"
        )
    else:
        await callback.message.answer(
            "⛔️ Подпишитесь для доступа:",
            reply_markup=subscription_menu(),
            parse_mode="Markdown"
        )