# handlers/settings.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from states import SettingsState
from models import Session, UserSettings
from keyboards import back_to_menu, settings_menu

router = Router()


@router.callback_query(F.data == "settings")
async def settings_main_menu(callback: types.CallbackQuery):
    with Session() as session:
        user = session.get(UserSettings, callback.from_user.id)

    text = "⚙️ **Настройки**\n\n"
    if user and user.wb_api_key:
        text += f"Текущий API-ключ: {'*' * 12}{user.wb_api_key[-4:]}\n"
    else:
        text += "API-ключ не установлен\n"

    await callback.message.edit_text(
        text,
        reply_markup=settings_menu(user),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "set_api_key")
async def set_api_key_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SettingsState.waiting_api_key)
    await callback.message.answer(
        "🔑 Введите ваш API-ключ Wildberries:",
        reply_markup=back_to_menu()
    )


@router.message(SettingsState.waiting_api_key)
async def process_api_key(message: types.Message, state: FSMContext):
    with Session() as session:
        user = session.get(UserSettings, message.from_user.id) or UserSettings(user_id=message.from_user.id)
        user.wb_api_key = message.text
        session.add(user)
        session.commit()

    await state.clear()
    await message.answer("✅ API-ключ успешно сохранен!", reply_markup=back_to_menu())


@router.callback_query(F.data == "delete_api_key")
async def delete_api_key_handler(callback: types.CallbackQuery):
    with Session() as session:
        user = session.get(UserSettings, callback.from_user.id)
        if user:
            user.wb_api_key = None
            session.commit()

    await callback.answer("🔑 API-ключ удален", show_alert=True)
    await settings_main_menu(callback)