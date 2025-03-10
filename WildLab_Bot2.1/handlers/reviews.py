# handlers/reviews.py
from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from models import UserSettings, Review, Session
from states import ReviewState
from keyboards import back_button, back_button_auto, back_button_auto2, back_button_auto3
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils.pagination import paginate_reviews
from utils.prompts import build_prompt
import logging
import time
from typing import Union
from utils.wb_api import WildberriesAPI
from models import Review
router = Router()
logger = logging.getLogger(__name__)


# ============ Заглушки для интеграций ============

async def get_unanswered_reviews(user_id: int) -> list:
    with Session() as session:
        user = session.get(UserSettings, user_id)
        if not user or not user.wb_api_key:
            logger.warning(f"User {user_id} has no WB API key configured")
            return []

        wb_api = WildberriesAPI(user.wb_api_key)
        try:
            reviews = await wb_api.get_unanswered_reviews()

            # Фильтрация пустых отзывов и преобразование типов
            processed_reviews = []
            for review in reviews:
                # Преобразуем булевы значения в строки
                review = {k: str(v) if isinstance(v, bool) else v for k, v in review.items()}

                # Проверяем наличие содержания
                has_content = any([
                    review.get("text"),  # Правильное поле из API
                    review.get("pros"),
                    review.get("cons"),
                    review.get("photoLinks")  # Проверка наличия фото
                ])

                if has_content:
                    processed_reviews.append(review)

            return processed_reviews

        except Exception as e:
            logger.error(f"WB API error: {e}")
            return []


def generate_reply(prompt: str) -> str:
    return f"Спасибо за ваш отзыв! Мы ценим ваше мнение."


async def send_review_reply(feedback_id: str, text: str, user_id: int) -> bool:
    with Session() as session:
        user = session.get(UserSettings, user_id)
        if not user or not user.wb_api_key:
            return False

        wb_api = WildberriesAPI(user.wb_api_key)
        return await wb_api.send_reply(feedback_id, text)

# ============ Периодическая проверка отзывов ============



# ============ Обработка отзывов пользователем ============
async def check_new_reviews(bot):
    """Фоновая задача для проверки новых отзывов"""
    logger.info("Starting scheduled reviews check")

    with Session() as session:
        try:
            users = session.query(UserSettings).all()
            for user in users:
                try:
                    # Получаем новые отзывы через API
                    raw_reviews = await get_unanswered_reviews(user.user_id)
                    if not raw_reviews:
                        continue

                    # Сохраняем новые отзывы в БД
                    new_reviews_count = 0
                    for review in raw_reviews:
                        try:
                            # Проверяем существование отзыва в БД
                            exists = session.query(Review).filter_by(
                                source_api_id=str(review["id"]),
                                user_id=user.user_id
                            ).first()

                            if not exists:
                                # Явное преобразование типов
                                new_review = Review(
                                    source_api_id=str(review.get("id", "")),  # Всегда строка
                                    stars=int(review.get("stars", 0)),
                                    comment=str(review.get("text", "")),  # WB API использует "text", а не "comment"
                                    pros=str(review.get("pros", "")),
                                    cons=str(review.get("cons", "")),
                                    photo_url=bool(review.get("photoLinks")),  # photoLinks есть в API, а не photo
                                    is_answered=False
                                )
                                session.add(new_review)
                                new_reviews_count += 1

                        except Exception as e:
                            logger.error(f"Error saving review {review.get('id')}: {str(e)}")

                    # Коммитим все изменения разом
                    session.commit()
                    logger.info(f"Saved {new_reviews_count} new reviews for user {user.user_id}")

                    # Отправляем уведомление пользователю
                    if user.notifications_enabled and new_reviews_count > 0:
                        try:
                            await bot.send_message(
                                user.user_id,
                                f"📬 Получено новых отзывов: {new_reviews_count}",
                                parse_mode="HTML"
                            )
                        except Exception as notify_error:
                            logger.error(f"Notification error: {notify_error}")

                    # Обработка автоответов
                    if user.auto_reply_enabled:
                        auto_replied = 0
                        for review in raw_reviews:
                            try:
                                # Проверяем условия для автоответа
                                if (user.auto_reply_five_stars
                                        and int(review.get("stars", 0)) == 5
                                        and not str(review.get("cons", "")).strip()):

                                    # Отправляем ответ
                                    success = await send_review_reply(
                                        feedback_id=str(review["id"]),
                                        text="Спасибо за ваш отзыв!",
                                        user_id=user.user_id
                                    )

                                    if success:
                                        # Получаем актуальную версию отзыва
                                        with Session() as inner_session:
                                            db_review = inner_session.query(Review).filter_by(
                                                source_api_id=str(review["id"]),
                                                user_id=user.user_id
                                            ).with_for_update().first()

                                            if db_review:
                                                db_review.is_answered = True
                                                inner_session.commit()
                                                logger.info(f"Marked review {review['id']} as answered")
                                    else:
                                        logger.error(f"Failed to send reply for review {review['id']}")
                                        # Можно добавить повторную попытку

                            except Exception as e:
                                logger.error(f"Auto-reply error: {str(e)}")

                        session.commit()
                        logger.info(f"Auto-replied to {auto_replied} reviews")

                except Exception as e:
                    logger.error(f"Error processing user {user.user_id}: {str(e)}")

        except Exception as e:
            logger.error(f"Global check error: {str(e)}")

@router.callback_query(F.data.startswith("manual_"))  # Новый обработчик
async def start_manual_reply(callback: types.CallbackQuery, state: FSMContext):
    try:
        review_id = int(callback.data.split("_")[1])
        await state.update_data(review_id=review_id)

        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад", callback_data=f"review_{review_id}")

        await callback.message.answer(
            "✍️ Напишите ваш ответ на отзыв:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(ReviewState.waiting_for_custom_reply)

    except Exception as e:
        logger.error(f"Error in start_manual_reply: {e}")
        await callback.answer("❌ Ошибка при запуске ручного ответа")


@router.callback_query(F.data == "write_own")  # Существующий обработчик
async def write_own_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("✍️ Напишите ваш собственный ответ:", reply_markup=back_button_auto())
    await state.set_state(ReviewState.waiting_for_custom_reply)


@router.message(ReviewState.waiting_for_custom_reply)
async def process_custom_reply(message: types.Message, state: FSMContext):
    try:
        # Получаем review_id из состояния
        data = await state.get_data()
        review_id = data.get("review_id")

        if not review_id:
            logger.error("Review ID not found in state")
            await message.answer("❌ Ошибка: отзыв не найден")
            return

        if not message.text:
            await message.answer("❌ Пожалуйста, введите текстовый ответ")
            return

        await state.update_data(generated_reply=message.text)

        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Отправить ответ", callback_data="send_reply")
        # Исправляем callback_data
        builder.button(text="◀️ Назад", callback_data=f"review_{review_id}")  # Правильный формат
        builder.adjust(1)

        await message.answer(
            f"📝 Ваш ответ готов к отправке:\n{message.text}",
            reply_markup=builder.as_markup()
        )

    except Exception as e:
        logger.error(f"Error in process_custom_reply: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте ещё раз.")


@router.callback_query(F.data == "back_to_current_review")
async def back_to_current_review_handler(callback: types.CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        review_id = data.get("review_id")

        if not review_id or not isinstance(review_id, int):
            raise ValueError("Invalid review_id in state")

        # Создаем искусственный callback с правильными данными
        fake_callback = types.CallbackQuery(
            data=f"review_{review_id}",
            message=callback.message,
            from_user=callback.from_user
        )

        await review_detail_handler(fake_callback, state)

    except Exception as e:
        logger.error(f"Error in back_to_current_review_handler: {str(e)}")
        await callback.answer("❌ Ошибка при возврате к отзыву")


@router.callback_query(F.data == "pending_reviews")
async def reviews_list_handler(callback: types.CallbackQuery, state: FSMContext):
    await check_new_reviews(callback.bot)
    try:
        user_id = callback.from_user.id
        text_template = "📋 *Список неотвеченных отзывов*\n\nВыберите отзыв для ответа:"
        items_per_page = 5

        with Session() as session:
            # Проверяем настройки пользователя
            user = session.get(UserSettings, user_id)
            if not user or not user.wb_api_key:
                await callback.message.edit_text(
                    "🔑 Для работы с отзывами необходимо настроить API-ключ в разделе настроек.",
                    reply_markup=back_button_auto(),
                    parse_mode="Markdown"
                )
                return

            # Получаем отзывы из БД
            db_reviews = session.query(Review).filter(
                Review.user_id == user_id,
                Review.is_answered == False
            ).order_by(Review.id.desc()).all()

            # Фильтруем пустые отзывы
            filtered_reviews = [
                r for r in db_reviews
                if any([r.comment.strip(), r.pros.strip(), r.cons.strip(), r.photo_url])
            ]

            if not filtered_reviews:
                await callback.message.edit_text(
                    "✅ Все отзывы обработаны!",
                    reply_markup=back_button_auto3()
                )
                return

            # Преобразуем в формат для пагинации
            formatted_reviews = []
            for review in filtered_reviews:
                formatted_reviews.append({
                    "id": review.source_api_id,
                    "stars": review.stars,
                    "comment": review.comment,
                    "pros": review.pros,
                    "cons": review.cons,
                    "photo": bool(review.photo_url)
                })

            # Пагинация
            data = await state.get_data()
            current_page = data.get("page", 0)
            total_pages = (len(formatted_reviews) + items_per_page - 1) // items_per_page

            # Корректируем номер страницы
            current_page = max(0, min(current_page, total_pages - 1))
            start_idx = current_page * items_per_page
            page_reviews = formatted_reviews[start_idx:start_idx + items_per_page]

            # Строим клавиатуру
            builder = InlineKeyboardBuilder()

            # Кнопки отзывов
            for review in page_reviews:
                btn_text = (
                    f"{review['stars']}⭐ "
                    f"{'📸 ' if review['photo'] else ''}"
                    f"{review['comment'][:15]}..."
                ).strip()

                builder.button(
                    text=btn_text,
                    callback_data=f"review_{review['id']}"
                )

            # Кнопки пагинации
            if total_pages > 1:
                pagination_row = []
                if current_page > 0:
                    pagination_row.append(InlineKeyboardButton(
                        text="◀️ Пред.",
                        callback_data=f"page_{current_page - 1}"
                    ))
                pagination_row.append(InlineKeyboardButton(
                    text=f"{current_page + 1}/{total_pages}",
                    callback_data="current_page"
                ))
                if current_page < total_pages - 1:
                    pagination_row.append(InlineKeyboardButton(
                        text="След. ▶️",
                        callback_data=f"page_{current_page + 1}"
                    ))

                builder.row(*pagination_row)

            # Кнопка возврата
            builder.row(InlineKeyboardButton(
                text="🔙 В главное меню",
                callback_data="main_menu"
            ))

            # Обновляем сообщение
            await callback.message.edit_text(
                text_template,
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )

            # Сохраняем текущую страницу
            await state.update_data(page=current_page)

    except Exception as e:
        logger.error(f"Error in pending_reviews: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            "⚠️ Произошла ошибка при загрузке отзывов. Попробуйте позже.",
            reply_markup=back_button_auto3()
        )


@router.callback_query(F.data.startswith("review_"))
async def review_detail_handler(callback: types.CallbackQuery, state: FSMContext):
    try:
        parts = callback.data.split("_")
        if len(parts) != 2 or not parts[1].isdigit():
            raise ValueError(f"Invalid review ID: {callback.data}")

        review_id = int(callback.data.split("_")[1])
        user_id = callback.from_user.id
        reviews = get_unanswered_reviews(user_id)
        review = next((r for r in reviews if r["id"] == review_id), None)
        if not review:
            await callback.message.edit_text("❌ Отзыв не найден.")
            return

        review_text = f"⭐ {review['stars']}\n"
        if review.get("photo"):
            review_text += f"📸 Фото: {'Да' if review.get('photo') == 'True' else 'Нет'}\n"
        if review.get("comment"):
            review_text += f"💬 Комментарий: {review['comment']}\n"
        if review.get("pros"):
            review_text += f"✅ Достоинства: {review['pros']}\n"
        if review.get("cons"):
            review_text += f"⚠️ Недостатки: {review['cons']}\n"

        builder = InlineKeyboardBuilder()
        builder.button(text="✍️ Ручной ответ", callback_data=f"manual_{review_id}")
        builder.button(text="🤖 Автогенерация", callback_data=f"generate_{review_id}")
        builder.button(text="◀️ Назад", callback_data="pending_reviews")
        builder.adjust(1)

        await callback.message.edit_text(
            f"{review_text}\nВыберите метод ответа:",
            reply_markup=builder.as_markup()
        )
        await state.update_data(review_id=review_id, regeneration_count=0)

    except Exception as e:
        logger.error(f"Error in review_detail_handler: {e}")
        await callback.message.edit_text("❌ Произошла ошибка. Попробуйте ещё раз.")


@router.callback_query(F.data.startswith("generate_"))
async def start_generation_flow(callback: types.CallbackQuery, state: FSMContext):
    review_id = int(callback.data.split("_")[1])
    await state.update_data(review_id=review_id)
    await callback.message.answer("✍️ Введите аргументы через запятую:")
    await state.set_state(ReviewState.waiting_for_arguments)


@router.message(ReviewState.waiting_for_arguments)
async def process_review_arguments(message: types.Message, state: FSMContext):
    try:
        arguments = [arg.strip() for arg in message.text.split(",") if arg.strip()]
        await state.update_data(arguments=arguments)

        builder = InlineKeyboardBuilder()
        builder.button(text="⏭ Пропустить", callback_data="skip_solution")
        builder.button(text="◀️ Назад", callback_data="back_to_reviews")
        builder.adjust(1)

        await message.answer(
            "💡 Хотите предложить решение проблемы? (Или нажмите 'Пропустить')",
            reply_markup=builder.as_markup()
        )
        await state.set_state(ReviewState.waiting_for_solution)

    except Exception as e:
        logger.error(f"Error in process_review_arguments: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте ещё раз.")


@router.callback_query(F.data == "skip_solution", ReviewState.waiting_for_solution)
async def handle_skip_solution(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(solution=None)
    await process_generation(callback, state)


@router.message(ReviewState.waiting_for_solution)
async def process_solution(message: types.Message, state: FSMContext):
    await state.update_data(solution=message.text)
    await process_generation(message, state)


async def process_generation(source: Union[types.Message, types.CallbackQuery], state: FSMContext):
    try:
        data = await state.get_data()
        is_regenerate = data.get("is_regenerate", False)

        with Session() as session:
            user_id = source.from_user.id
            user = session.get(UserSettings, user_id)
            reviews = get_unanswered_reviews(user_id)
            review = next((r for r in reviews if r["id"] == data["review_id"]), None)

            # Генерация промпта
            prompt = build_prompt(
                review=review,
                user=user,
                arguments=data.get("arguments", []),
                solution=data.get("solution")
            )

            # Добавляем перефразирование только при регенерации
            if is_regenerate:
                prompt += "\n\nПопробуй написать другими словами:"
                await state.update_data(is_regenerate=False)

            generated_reply = generate_reply(prompt)
            await state.update_data(generated_reply=generated_reply)

            builder = InlineKeyboardBuilder()
            builder.button(text="🔄 Сгенерировать заново", callback_data="regenerate")
            builder.button(text="✍️ Ручной ответ", callback_data="write_own")
            builder.button(text="✅ Отправить", callback_data="send_reply")
            builder.button(text="◀️ Назад", callback_data="back_to_reviews")
            builder.adjust(1)

            if isinstance(source, types.Message):
                await source.answer(f"📄 **Тестовый промпт**:\n{prompt}")
                await source.answer(f"🤖 Ответ:\n{generated_reply}", reply_markup=builder.as_markup())
            else:
                await source.message.answer(f"📄 **Тестовый промпт**:\n{prompt}")
                await source.message.answer(f"🤖 Ответ:\n{generated_reply}", reply_markup=builder.as_markup())

    except Exception as e:
        logger.error(f"Error in process_generation: {e}")
        error_msg = "❌ Произошла ошибка. Попробуйте ещё раз."
        if isinstance(source, types.Message):
            await source.answer(error_msg)
        else:
            await source.message.answer(error_msg)


@router.callback_query(F.data == "regenerate")
async def regenerate_reply(callback: types.CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        count = data.get("regeneration_count", 0)
        if count >= 3:
            await callback.answer("Лимит генерации достигнут. Напишите ответ вручную.", show_alert=True)
            return

        await state.update_data(
            regeneration_count=count + 1,
            is_regenerate=True  # Устанавливаем флаг перефразирования
        )

        with Session() as session:
            user = session.get(UserSettings, callback.from_user.id)
            reviews = get_unanswered_reviews(callback.from_user.id)
            review = next((r for r in reviews if r["id"] == data["review_id"]), None)

            # Генерация нового промпта с флагом перефразирования
            new_prompt = build_prompt(
                review=review,
                user=user,
                arguments=data.get("arguments", []),
                solution=data.get("solution")
            ) + "\n\nПопробуй написать другими словами:"

            new_reply = generate_reply(new_prompt)
            await state.update_data(generated_reply=new_reply)

            builder = InlineKeyboardBuilder()
            builder.button(text="🔄 Сгенерировать заново", callback_data="regenerate")
            builder.button(text="✍️ Ручной ответ", callback_data="write_own")
            builder.button(text="✅ Отправить", callback_data="send_reply")
            builder.button(text="◀️ Назад", callback_data="back_to_reviews")
            builder.adjust(1)

            await callback.message.edit_text(f"🤖 Новый ответ:\n{new_reply}")
            await callback.message.edit_reply_markup(reply_markup=builder.as_markup())

    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            await callback.answer("Обновите аргументы для новой генерации")
        else:
            logger.error(f"Error in regenerate_reply: {e}")
            await callback.answer("❌ Произошла ошибка. Попробуйте ещё раз.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in regenerate_reply: {e}")
        await callback.answer("❌ Произошла ошибка. Попробуйте ещё раз.", show_alert=True)


@router.callback_query(F.data == "send_reply")
async def send_reply_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    success = await send_review_reply(
        feedback_id=data["review_id"],
        text=data["generated_reply"],
        user_id=callback.from_user.id
    )

    if success:
        await callback.answer("✅ Ответ успешно отправлен")
    else:
        await callback.answer("❌ Ошибка отправки")


@router.callback_query(F.data == "back_to_reviews")
async def back_to_reviews_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await reviews_list_handler(callback, state)


@router.callback_query(F.data.startswith("page_"))
async def handle_pagination(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[1])
    await state.update_data(page=page)
    await reviews_list_handler(callback, state)


# ============ Запуск фоновой задачи ============

async def on_startup(dp):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_new_reviews, 'interval', minutes=5, args=(dp.bot,))
    scheduler.start()


if __name__ == "__main__":
    from aiogram import executor

    executor.start_polling(dp, on_startup=on_startup)