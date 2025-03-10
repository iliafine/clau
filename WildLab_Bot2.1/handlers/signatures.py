from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from models import Session, UserSettings
from states import AutoReplyState
from keyboards import back_button

router = Router()


@router.callback_query(F.data == "signatures")
async def signatures_handler(callback: types.CallbackQuery):
    with Session() as session:
        user = session.get(UserSettings, callback.from_user.id)

    text = (
        "✍️ **Фирменные подписи**\n\n"
        f"Приветствие: {user.greeting or 'Не установлено'}\n"
        f"Прощание: {user.farewell or 'Не установлено'}\n\n"
        "Выберите действие:"
    )

    builder = InlineKeyboardBuilder()
    if user.greeting:
        builder.button(text="✏ Изменить приветствие", callback_data="add_greeting")
        builder.button(text="❌ Удалить приветствие", callback_data="delete_greeting")
    else:
        builder.button(text="🖋 Добавить приветствие", callback_data="add_greeting")

    if user.farewell:
        builder.button(text="✏ Изменить прощание", callback_data="add_farewell")
        builder.button(text="❌ Удалить прощание", callback_data="delete_farewell")
    else:
        builder.button(text="🖋 Добавить прощание", callback_data="add_farewell")

    builder.button(text="◀️ Назад", callback_data="auto_reply_settings")
    builder.adjust(1)

    # Отправляем новое сообщение вместо редактирования
    await callback.message.answer(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "add_greeting")
async def add_greeting_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AutoReplyState.waiting_greeting)
    await callback.message.answer(
        "📝 Введите ваше фирменное приветствие:",
        reply_markup=back_button()
    )


@router.callback_query(F.data == "add_farewell")
async def add_farewell_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AutoReplyState.waiting_farewell)
    await callback.message.answer(
        "📝 Введите вашу фирменную прощальную фразу:",
        reply_markup=back_button()
    )


@router.message(AutoReplyState.waiting_greeting)
async def process_greeting(message: types.Message, state: FSMContext):
    with Session() as session:
        user = session.get(UserSettings, message.from_user.id) or UserSettings(user_id=message.from_user.id)
        user.greeting = message.text
        session.add(user)
        session.commit()

    await state.clear()
    await message.answer("✅ Приветствие успешно сохранено!")

    # Отправляем новое сообщение вместо редактирования
    await signatures_handler(types.CallbackQuery(
        from_user=message.from_user,
        id="dummy",
        chat_instance="dummy",
        message=message
    ))


@router.message(AutoReplyState.waiting_farewell)
async def process_farewell(message: types.Message, state: FSMContext):
    with Session() as session:
        user = session.get(UserSettings, message.from_user.id) or UserSettings(user_id=message.from_user.id)
        user.farewell = message.text
        session.add(user)
        session.commit()

    await state.clear()
    await message.answer("✅ Прощание успешно сохранено!")

    # Отправляем новое сообщение вместо редактирования
    await signatures_handler(types.CallbackQuery(
        from_user=message.from_user,
        id="dummy",
        chat_instance="dummy",
        message=message
    ))


@router.callback_query(F.data == "delete_greeting")
async def delete_greeting_handler(callback: types.CallbackQuery):
    with Session() as session:
        user = session.get(UserSettings, callback.from_user.id)
        if user:
            user.greeting = None
            session.commit()

    await callback.answer("Приветствие удалено", show_alert=True)
    # Отправляем новое сообщение вместо редактирования
    await signatures_handler(callback)


@router.callback_query(F.data == "delete_farewell")
async def delete_farewell_handler(callback: types.CallbackQuery):
    with Session() as session:
        user = session.get(UserSettings, callback.from_user.id)
        if user:
            user.farewell = None
            session.commit()

    await callback.answer("Прощание удалено", show_alert=True)
    # Отправляем новое сообщение вместо редактирования
    await signatures_handler(callback)
