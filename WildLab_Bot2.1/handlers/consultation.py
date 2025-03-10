from aiogram import Router, types
from keyboards import back_to_menu

router = Router()

CONSULT_TEXT = (
    '💬 Чтобы получить индивидуальную консультацию, напиши [Илье](https://t.me/Ilyachuiak) в личные сообщения.\n\n *Обязательно укажи, что ты из бота WildLab.*'
)

@router.callback_query(lambda c: c.data == "consult")
async def consult_handler(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
        await callback.message.answer(
            CONSULT_TEXT,
            reply_markup=back_to_menu(),
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Consultation error: {e}")
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)