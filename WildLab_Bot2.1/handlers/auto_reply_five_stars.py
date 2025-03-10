# handlers/auto_reply_five_stars.py
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from models import Session, UserSettings
from keyboards import back_button

router = Router()


@router.callback_query(F.data == "auto_reply_five_stars")
async def auto_reply_five_stars_handler(callback: types.CallbackQuery):
    with Session() as session:
        user = session.get(UserSettings, callback.from_user.id)

    status = "✅ Включено" if user.auto_reply_five_stars else "❌ Выключено"

    text = (
        "⭐ **Автоответ на 5 звезд**\n\n"
        "Эта функция автоматически отвечает на отзывы с 5 звездами, если в них нет указанных недостатков.\n\n"
        f"Статус: {status}\n\n"
        "Выберите действие:"
    )

    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"{'❌ Выключить' if user.auto_reply_five_stars else '✅ Включить'} автоответ",
        callback_data="toggle_five_stars"
    )
    builder.button(text="◀️ Назад", callback_data="auto_reply_settings")
    builder.adjust(1)

    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "toggle_five_stars")
async def toggle_five_stars_handler(callback: types.CallbackQuery):
    with Session() as session:
        user = session.get(UserSettings, callback.from_user.id)
        if not user:
            user = UserSettings(user_id=callback.from_user.id)
            session.add(user)

        user.auto_reply_five_stars = not user.auto_reply_five_stars
        session.commit()

    await auto_reply_five_stars_handler(callback)