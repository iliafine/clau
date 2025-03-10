from aiogram import Router, Bot, types
from aiogram.utils.keyboard import InlineKeyboardButton, InlineKeyboardBuilder
from aiogram.types import FSInputFile
from config import Config
from keyboards import tables_menu, subscription_menu
from services.subscription import check_subscription
import logging

router = Router()
logger = logging.getLogger(__name__)


def create_table_keyboard(url: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Открыть таблицу📊", url=url),
        InlineKeyboardButton(text="◀️ Назад", callback_data="tables"),
        width=1
    )
    return builder


async def send_table(
        callback: types.CallbackQuery,
        photo_path: str,
        caption: str,
        url: str
):
    try:
        await callback.message.delete()
        photo = FSInputFile(photo_path)

        await callback.message.answer_photo(
            photo=photo,
            caption=caption,
            reply_markup=create_table_keyboard(url).as_markup(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error sending table: {e}")
        await callback.message.answer("⚠️ Произошла ошибка при загрузке таблицы")


@router.callback_query(lambda c: c.data == "tables")
async def handle_tables(callback: types.CallbackQuery, bot: Bot):
    try:
        await callback.message.delete()

        if await check_subscription(bot, callback.from_user.id):
            await callback.message.answer(
            '📊 Здесь ты найдешь * бесплатные * таблицы, которые помогут оптимизировать работу с * Wildberries. *\n\n Выбери таблицу, которая тебе нужна:'
            ,
                reply_markup=tables_menu(),
                parse_mode="Markdown"
            )
        else:
            await callback.message.answer(
                "Для доступа к таблицам подпишитесь на канал:",
                reply_markup=subscription_menu(),
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Tables menu error: {e}")


@router.callback_query(lambda c: c.data == "price_cost")
async def handle_price_table(callback: types.CallbackQuery):
    await send_table(
        callback=callback,
        photo_path=Config.INSTRUCTIONS[0],
        caption=(
            "⚖️ *Таблица проверки цены* поможет тебе проанализировать спрос и выручку при изменении цены.\n"
            "💡 *Чем эта таблица уникальна?*\n"
            "1️⃣ Включает интеграцию юнит-экономики.\n"
            "2️⃣ Показывает доходность с одного вложенного рубля.\n"
            "3️⃣ *Она абсолютно бесплатная!*\n\n"
            "🛠️ *Как это работает:*\n"
            "Заполняешь желтые поля, вводишь текущие показатели продаж, меняешь цену, добавляешь данные и сразу видишь, как это влияет на прибыль. Всё просто и интуитивно понятно!\n"
            "Скриншот как копировать таблицу прикреплен."
        ),
        url="https://docs.google.com/spreadsheets/d/1SPezBUYpHdiGtJEUO8_yQ1DgDo6zHsaTFy-9V9hg5R4/edit"
    )


@router.callback_query(lambda c: c.data == "china_cost")
async def handle_china_table(callback: types.CallbackQuery):
    await send_table(
        callback=callback,
        photo_path=Config.INSTRUCTIONS[0],
        caption=(
            "🇨🇳*Эта таблица поможет тебе рассчитать себестоимость товара, учитывая все издержки на логистику из Китая.*\n"
            "📖*Инструкция:*\n"
            "1️⃣ Скопируй таблицу себе.\n"
            "2️⃣ Заполни желтые ячейки.\n"
            "3️⃣ Для удобства в таблице есть два независимых калькулятора. Их заполнять не обязательно (калькулятор курса и разделения общего веса)\n\n"
            "*Скриншот как копировать таблицу прикреплен.*"
        ),
        url="https://docs.google.com/spreadsheets/d/1KCN7apSYrex8sNK3QY4fCAHK1VXYVd-AFoyUmPgGMZg/edit"
    )