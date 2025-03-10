from aiogram import Router, types
from aiogram.filters import Command
from config import Config
from keyboards import main_menu

router = Router()


@router.message(Command("start"))
@router.callback_query(lambda c: c.data == "start")
async def send_welcome(event: types.Message | types.CallbackQuery):
    welcome_text = (
        "👋 *Привет!*\n"
        'Я бот канала WildLab — твой помощник в работе с маркетплейсами.\n\n'
        '💡 *Я могу:*\n'
        '• Предоставить полезные таблицы, которые упрощают управление продажами.\n'
        '• Записать тебя на консультацию, чтобы ты получил ответы на свои вопросы.\n\n'
        '*Давай начнем? Выбирай действие:*'
    )

    if isinstance(event, types.CallbackQuery):
        await event.message.delete()
        await event.message.answer(welcome_text, reply_markup=main_menu(), parse_mode="Markdown")
    else:
        await event.answer(welcome_text, reply_markup=main_menu(), parse_mode="Markdown")