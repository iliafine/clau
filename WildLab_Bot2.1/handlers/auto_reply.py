from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from models import Session, UserSettings
from states import AutoReplyState
from keyboards import back_button, auto_reply_settings_menu

router = Router()

@router.callback_query(lambda c: c.data == "auto_reply")
async def auto_reply_handler(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="⚙️ Настройки автоответов", callback_data="auto_reply_settings")
    builder.button(text="📋 Необработанные отзывы", callback_data="pending_reviews")
    builder.button(text="◀️ На главную", callback_data="start")
    builder.adjust(1)

    await callback.message.edit_text(
        "🤖 **Автоответы на отзывы**\n\nВыберите раздел:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )



@router.callback_query(F.data == "auto_reply_settings")
async def auto_reply_settings_handler(callback: types.CallbackQuery):
    with Session() as session:
        user = session.get(UserSettings, callback.from_user.id)

    text = (
        "⚙️ **Настройки автоответов**\n\n"
        f"🔔 Уведомления: {'Включены' if user.notifications_enabled else 'Выключены'}\n\n"
        "Выберите настройку для изменения:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=auto_reply_settings_menu(user),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "toggle_notifications")
async def toggle_notifications_handler(callback: types.CallbackQuery):
    with Session() as session:
        user = session.get(UserSettings, callback.from_user.id)
        if not user:
            user = UserSettings(user_id=callback.from_user.id)
            session.add(user)

        user.notifications_enabled = not user.notifications_enabled
        session.commit()

    await auto_reply_settings_handler(callback)

@router.callback_query(F.data == "toggle_auto_reply")
async def toggle_auto_reply_handler(callback: types.CallbackQuery):
    with Session() as session:
        user = session.get(UserSettings, callback.from_user.id)
        if not user:
            user = UserSettings(user_id=callback.from_user.id)
            session.add(user)

        user.auto_reply_enabled = not user.auto_reply_enabled
        session.commit()

    await auto_reply_settings_handler(callback)

