# handlers/reviews.py
import logging
import asyncio
from typing import Union, Dict, Any, List, Optional
from datetime import datetime, timedelta
import json

from aiogram import Router, types, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from models import UserSettings, Review, Session
from states import ReviewState
from keyboards import (
    back_button, back_button_auto, back_button_auto2,
    back_button_auto3
)
from utils.wb_api import WildberriesAPI, normalize_review_fields
from utils.prompts import build_prompt

router = Router()
logger = logging.getLogger(__name__)


# ============ Вспомогательные функции ============

async def get_unanswered_reviews(user_id: int) -> List[Dict[str, Any]]:
    """
    Получение необработанных отзывов пользователя

    Args:
        user_id: ID пользователя

    Returns:
        List[Dict[str, Any]]: Список отзывов
    """
    with Session() as session:
        user = session.get(UserSettings, user_id)
        if not user or not user.wb_api_key:
            logger.warning(f"User {user_id} has no WB API key configured")
            return []

        try:
            # Инициализируем API
            wb_api = WildberriesAPI(user.wb_api_key)

            # Получаем отзывы через API
            raw_reviews = await wb_api.get_unanswered_reviews(is_answered=False)

            # Нормализуем данные отзывов
            normalized_reviews = []
            for review in raw_reviews:
                normalized = await normalize_review_fields(review)

                # Проверяем, содержит ли отзыв какую-либо информацию
                has_content = any([
                    normalized["comment"].strip(),
                    normalized["pros"].strip() and normalized["pros"].lower() != "не указаны",
                    normalized["cons"].strip() and normalized["cons"].lower() != "не указаны",
                    normalized["photo_url"]
                ])

                if has_content:
                    normalized_reviews.append(normalized)

            logger.info(f"Fetched {len(normalized_reviews)} valid reviews for user {user_id}")
            return normalized_reviews

        except Exception as e:
            logger.error(f"WB API error: {e}", exc_info=True)
            return []


def generate_reply(prompt: str) -> str:
    """
    Временная заглушка для генерации ответа на отзыв
    В будущем будет заменена на интеграцию с ИИ

    Args:
        prompt: Текст промпта

    Returns:
        str: Сгенерированный ответ
    """
    # Базовый ответ в зависимости от наличия слов в промпте
    if "Достоинства:" in prompt and "не указаны" not in prompt:
        return "Большое спасибо за ваш отзыв и высокую оценку нашего товара! Мы очень рады, что вы отметили его достоинства. Будем и дальше стараться радовать вас качеством нашей продукции!"
    elif "Недостатки:" in prompt and "не указаны" not in prompt:
        return "Благодарим за ваш отзыв. Нам очень жаль, что возникли проблемы с товаром. Мы обязательно учтем ваши замечания для улучшения качества. Если вам потребуется дополнительная помощь, пожалуйста, свяжитесь с нами через чат поддержки."
    else:
        return "Спасибо за ваш отзыв! Мы ценим ваше мнение и стараемся постоянно улучшать качество наших товаров и сервиса. Будем рады видеть вас снова!"


async def send_review_reply(feedback_id: str, text: str, user_id: int) -> bool:
    """
    Отправляет ответ на отзыв через API Wildberries

    Args:
        feedback_id: ID отзыва
        text: Текст ответа
        user_id: ID пользователя

    Returns:
        bool: Результат операции
    """
    try:
        # Получаем API-ключ пользователя
        with Session() as session:
            user = session.get(UserSettings, user_id)
            if not user or not user.wb_api_key:
                logger.error(f"User {user_id} has no API key")
                return False

            # Инициализируем API
            wb_api = WildberriesAPI(user.wb_api_key)

            # Отправляем ответ
            result = await wb_api.send_reply(
                feedback_id=feedback_id,
                text=text
            )

            if result:
                # Обновляем статус отзыва в базе данных
                review = session.query(Review).filter_by(
                    source_api_id=feedback_id,
                    user_id=user_id
                ).first()

                if review:
                    review.is_answered = True
                    review.response = text
                    session.commit()
                    logger.info(f"Updated review {feedback_id} status for user {user_id}")

                return True
            else:
                logger.error(f"Failed to send reply for review {feedback_id}")
                return False

    except Exception as e:
        logger.error(f"Error sending reply: {e}", exc_info=True)
        return False


# ============ Основной обработчик проверки отзывов ============

async def check_new_reviews(bot: Bot) -> None:
    """
    Фоновая задача для проверки новых отзывов

    Args:
        bot: Экземпляр бота для отправки уведомлений
    """
    logger.info("Starting scheduled reviews check")

    with Session() as session:
        try:
            # Получаем всех пользователей
            users = session.query(UserSettings).all()

            for user in users:
                if not user.wb_api_key:
                    continue

                try:
                    # Инициализируем API
                    wb_api = WildberriesAPI(user.wb_api_key)

                    # Получаем неотвеченные отзывы
                    raw_reviews = await wb_api.get_unanswered_reviews(is_answered=False)
                    if not raw_reviews:
                        logger.debug(f"No new reviews for user {user.user_id}")
                        continue

                    # Нормализуем и обрабатываем отзывы
                    new_reviews_count = 0
                    for review in raw_reviews:
                        try:
                            # Нормализуем данные отзыва
                            normalized = await normalize_review_fields(review)

                            # Проверяем наличие отзыва в БД
                            exists = session.query(Review).filter_by(
                                source_api_id=normalized["source_api_id"],
                                user_id=user.user_id
                            ).first()

                            if not exists:
                                # Проверяем, содержит ли отзыв какую-либо информацию
                                has_content = any([
                                    normalized.get("comment", "").strip(),
                                    normalized.get("pros", "").strip() and normalized.get("pros",
                                                                                          "").lower() != "не указаны",
                                    normalized.get("cons", "").strip() and normalized.get("cons",
                                                                                          "").lower() != "не указаны",
                                    normalized.get("photo_url", False)
                                ])

                                if has_content:
                                    # Добавляем ID пользователя
                                    normalized["user_id"] = user.user_id
                                    photo_urls_json = json.dumps(normalized.get("photo_urls", [])) if normalized.get(
                                        "photo_urls") else "[]"

                                    # Создаем новую запись в БД
                                    # Безопасно выбираем только нужные поля для модели Review
                                    new_review = Review(
                                        source_api_id=normalized["source_api_id"],
                                        user_id=user.user_id,
                                        stars=normalized.get("stars", 0),
                                        comment=normalized.get("comment", ""),
                                        pros=normalized.get("pros", ""),
                                        cons=normalized.get("cons", ""),
                                        photo_url=normalized.get("photo_url", False),
                                        photo_urls=normalized.get("photo_urls", "[]"),  # JSON-строка с URL
                                        response=normalized.get("response", ""),
                                        is_answered=normalized.get("is_answered", False),
                                        product_name=normalized.get("product_name", ""),
                                        product_id=normalized.get("product_id", ""),
                                        supplier_article=normalized.get("supplier_article", ""),
                                        subject_name=normalized.get("subject_name", "")  # Добавлено поле типа товара
                                    )
                                    session.add(new_review)
                                    new_reviews_count += 1

                        except Exception as review_error:
                            logger.error(f"Error processing review: {review_error}", exc_info=True)

                    # Сохраняем изменения в БД
                    if new_reviews_count > 0:
                        session.commit()
                        logger.info(f"Saved {new_reviews_count} new reviews for user {user.user_id}")

                        # Отправляем уведомление пользователю
                        if user.notifications_enabled:
                            try:
                                # Формируем текст уведомления в зависимости от количества отзывов
                                if new_reviews_count == 1:
                                    text = "📩 У вас 1 новый отзыв!"
                                else:
                                    text = f"📩 У вас {new_reviews_count} новых отзывов!"

                                # Создаем клавиатуру для просмотра отзывов
                                builder = InlineKeyboardBuilder()
                                builder.button(
                                    text="📋 Посмотреть отзывы",
                                    callback_data="pending_reviews"
                                )

                                # Отправляем уведомление
                                await bot.send_message(
                                    user.user_id,
                                    text,
                                    reply_markup=builder.as_markup()
                                )

                                logger.info(f"Notification sent to user {user.user_id}")

                            except Exception as notify_error:
                                logger.error(f"Failed to send notification: {notify_error}", exc_info=True)

                    # Проверяем необходимость автоответов
                    if user.auto_reply_enabled:
                        auto_replied_count = await process_auto_replies(user, wb_api, session)
                        if auto_replied_count > 0:
                            logger.info(f"Auto-replied to {auto_replied_count} reviews for user {user.user_id}")

                except Exception as user_error:
                    logger.error(f"Error processing user {user.user_id}: {user_error}", exc_info=True)

        except Exception as global_error:
            logger.error(f"Global check error: {global_error}", exc_info=True)

async def process_auto_replies(user: UserSettings, wb_api: WildberriesAPI, session: Session) -> int:
    """
    Обрабатывает автоответы на отзывы

    Args:
        user: Настройки пользователя
        wb_api: Экземпляр API Wildberries
        session: Сессия БД

    Returns:
        int: Количество отправленных автоответов
    """
    auto_replied_count = 0

    try:
        # Получаем неотвеченные отзывы из БД
        reviews = session.query(Review).filter_by(
            user_id=user.user_id,
            is_answered=False
        ).all()

        for review in reviews:
            try:
                # Проверяем условия для автоответа на отзывы с 5 звездами
                if (user.auto_reply_five_stars and
                        review.stars == 5 and
                        (not review.cons or review.cons.strip() == "" or review.cons.lower() == "не указаны")):

                    # Формируем текст автоответа
                    auto_reply = "Спасибо за вашу высокую оценку! Мы очень рады, что вам понравился наш товар. Будем и дальше стараться радовать вас качеством нашей продукции."

                    # Добавляем подписи пользователя, если они есть
                    if user.greeting:
                        auto_reply = f"{user.greeting} {auto_reply}"
                    if user.farewell:
                        auto_reply = f"{auto_reply} {user.farewell}"

                    # Отправляем ответ через API
                    success = await wb_api.send_reply(
                        feedback_id=review.source_api_id,
                        text=auto_reply
                    )

                    if success:
                        # Обновляем статус отзыва в БД
                        review.is_answered = True
                        review.response = auto_reply
                        auto_replied_count += 1
                        logger.info(f"Auto-replied to review {review.source_api_id}")
                    else:
                        logger.error(f"Failed to auto-reply to review {review.source_api_id}")

            except Exception as e:
                logger.error(f"Error processing auto-reply for review {review.source_api_id}: {e}", exc_info=True)

        # Сохраняем изменения в БД
        if auto_replied_count > 0:
            session.commit()

        return auto_replied_count

    except Exception as e:
        logger.error(f"Error in process_auto_replies: {e}", exc_info=True)
        return 0


# ============ Обработчики команд и колбэков ============

@router.callback_query(F.data == "pending_reviews")
async def reviews_list_handler(callback: types.CallbackQuery, state: FSMContext):
    """
    Обработчик для показа списка неотвеченных отзывов

    Args:
        callback: Колбэк от кнопки
        state: Состояние FSM
    """
    # Показываем индикатор загрузки
    await callback.answer("Загрузка отзывов...")

    try:
        # Проверяем, содержит ли текущее сообщение фотографию
        # Если да, мы не можем его редактировать с помощью edit_text,
        # поэтому удаляем и отправляем новое
        data = await state.get_data()
        has_photo_message = data.get("has_photo", False)

        if has_photo_message:
            # Удаляем сообщение с фото и будем отправлять новое
            try:
                await callback.message.delete()
            except Exception as e:
                logger.error(f"Error deleting message with photo: {e}")

            need_new_message = True
        else:
            # Обычное текстовое сообщение, можем редактировать
            need_new_message = False

        # Обновляем список отзывов
        await check_new_reviews(callback.bot)

        user_id = callback.from_user.id
        items_per_page = 5

        with Session() as session:
            # Проверяем настройки пользователя
            user = session.get(UserSettings, user_id)
            if not user or not user.wb_api_key:
                if need_new_message:
                    await callback.message.answer(
                        "🔑 Для работы с отзывами необходимо настроить API-ключ в разделе настроек.",
                        reply_markup=back_button_auto2(),
                        parse_mode="Markdown"
                    )
                else:
                    await callback.message.edit_text(
                        "🔑 Для работы с отзывами необходимо настроить API-ключ в разделе настроек.",
                        reply_markup=back_button_auto2(),
                        parse_mode="Markdown"
                    )
                return

            # Получаем отзывы из БД
            db_reviews = session.query(Review).filter(
                Review.user_id == user_id,
                Review.is_answered == False
            ).order_by(Review.id.desc()).all()

            # Фильтруем пустые отзывы
            filtered_reviews = []
            for r in db_reviews:
                if ((r.comment and r.comment.strip()) or
                        (r.pros and r.pros.strip() and r.pros.lower() != "не указаны") or
                        (r.cons and r.cons.strip() and r.cons.lower() != "не указаны") or
                        r.photo_url):
                    filtered_reviews.append(r)

            # Если нет отзывов, показываем соответствующее сообщение
            if not filtered_reviews:
                if need_new_message:
                    await callback.message.answer(
                        "✅ Все отзывы обработаны!",
                        reply_markup=back_button_auto3(),
                        parse_mode="Markdown"
                    )
                else:
                    await callback.message.edit_text(
                        "✅ Все отзывы обработаны!",
                        reply_markup=back_button_auto3(),
                        parse_mode="Markdown"
                    )
                return

            # Получаем текущую страницу из состояния
            current_page = data.get("page", 0)

            # Вычисляем общее количество страниц
            total_pages = (len(filtered_reviews) + items_per_page - 1) // items_per_page

            # Корректируем номер страницы
            if current_page >= total_pages:
                current_page = 0

            start_idx = current_page * items_per_page
            end_idx = min(start_idx + items_per_page, len(filtered_reviews))

            # Подготавливаем данные для отображения
            text = "📋 *Список неотвеченных отзывов*\n\nВыберите отзыв для ответа:"

            # Строим клавиатуру с отзывами
            builder = InlineKeyboardBuilder()

            for review in filtered_reviews[start_idx:end_idx]:
                # Формируем превью отзыва в компактном формате
                stars = "⭐" * review.stars  # Звезды в виде эмодзи

                # Добавляем иконку фото только если у отзыва действительно есть фотографии
                has_real_photos = False
                if review.photo_url and review.photo_urls:
                    try:
                        photo_urls = json.loads(review.photo_urls)
                        has_real_photos = bool(photo_urls)
                    except:
                        has_real_photos = False

                photo_icon = "📸 " if has_real_photos else ""

                # Создаем текст кнопки в формате: "⭐⭐⭐⭐⭐ 📸"
                btn_text = f"{stars} {photo_icon}"

                # Добавляем короткое превью комментария, если есть место
                if review.comment and len(btn_text) < 45:
                    # Обрезаем комментарий
                    max_comment_length = 45 - len(btn_text)
                    if len(review.comment) > max_comment_length:
                        comment_preview = review.comment[:max_comment_length] + "..."
                    else:
                        comment_preview = review.comment

                    # Добавляем комментарий к тексту кнопки
                    btn_text += comment_preview

                builder.button(
                    text=btn_text,
                    callback_data=f"review_{review.source_api_id}"
                )

            # Добавляем кнопки пагинации
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

            if pagination_row:
                builder.row(*pagination_row)

            # Добавляем кнопку возврата
            builder.row(InlineKeyboardButton(
                text="◀️ Назад",
                callback_data="auto_reply"
            ))

            # Обновляем или отправляем новое сообщение
            if need_new_message:
                await callback.message.answer(
                    text,
                    reply_markup=builder.as_markup(),
                    parse_mode="Markdown"
                )
            else:
                await callback.message.edit_text(
                    text,
                    reply_markup=builder.as_markup(),
                    parse_mode="Markdown"
                )

            # Сохраняем текущую страницу и сбрасываем флаг фото
            await state.update_data(page=current_page, has_photo=False)

    except Exception as e:
        logger.error(f"Error in reviews_list_handler: {e}", exc_info=True)
        # В случае ошибки пробуем отправить новое сообщение
        try:
            await callback.message.answer(
                "⚠️ Произошла ошибка при загрузке отзывов. Попробуйте позже.",
                reply_markup=back_button_auto3()
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("page_"))
async def handle_pagination(callback: types.CallbackQuery, state: FSMContext):
    """
    Обработчик пагинации списка отзывов

    Args:
        callback: Колбэк от кнопки
        state: Состояние FSM
    """
    try:
        # Извлекаем номер страницы из callback_data
        page = int(callback.data.split("_")[1])

        # Проверяем, не сообщение ли это с фотографией
        data = await state.get_data()
        has_photo_message = data.get("has_photo", False)

        # Сохраняем новую страницу в состоянии и сбрасываем флаг фото
        # (при пагинации всегда будет текстовое сообщение)
        await state.update_data(page=page, has_photo=False)

        # Если текущее сообщение с фото, его нельзя редактировать
        if has_photo_message:
            try:
                # Удаляем сообщение с фото
                await callback.message.delete()
            except Exception as e:
                logger.error(f"Error deleting message with photo during pagination: {e}")

        # Вызываем стандартный обработчик списка отзывов с обновленной страницей
        await reviews_list_handler(callback, state)

    except Exception as e:
        logger.error(f"Error in handle_pagination: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при переключении страницы", show_alert=True)

@router.callback_query(F.data.startswith("review_"))
async def review_detail_handler(callback: types.CallbackQuery, state: FSMContext):
    """
    Обработчик для показа детальной информации об отзыве

    Args:
        callback: Колбэк от кнопки
        state: Состояние FSM
    """
    try:
        # Извлекаем ID отзыва из callback_data
        review_id = callback.data.split("_")[1]
        user_id = callback.from_user.id

        # Получаем данные отзыва из БД
        with Session() as session:
            review = session.query(Review).filter_by(
                source_api_id=review_id,
                user_id=user_id,
                is_answered=False
            ).first()

            if not review:
                await callback.message.edit_text(
                    "❌ Отзыв не найден или уже был обработан.",
                    reply_markup=back_button_auto3()
                )
                return

            # Формируем текст с информацией об отзыве
            stars_text = "⭐" * review.stars

            # Используем артикул продавца supplierArticle
            supplier_article = review.supplier_article if review.supplier_article else "Не указан"
            product_name = review.product_name if review.product_name else ""

            review_text = f"*Артикул:* {supplier_article}\n"

            if product_name:
                review_text += f"*Товар:* {product_name}\n"

            review_text += f"\n{stars_text}\n\n"

            if review.comment and review.comment.strip():
                review_text += f"*Комментарий:*\n{review.comment}\n\n"

            if review.pros and review.pros.strip() and review.pros.lower() != "не указаны":
                review_text += f"*Достоинства:*\n{review.pros}\n\n"

            if review.cons and review.cons.strip() and review.cons.lower() != "не указаны":
                review_text += f"*Недостатки:*\n{review.cons}\n\n"

            # Проверяем наличие фотографий в базе данных
            has_photos = review.photo_url
            photo_urls = []

            if has_photos and review.photo_urls:
                try:
                    # Парсим JSON-строку с URL фотографий
                    photo_urls = json.loads(review.photo_urls)
                    logger.info(f"Parsed photo_urls from DB: {photo_urls}")

                    if not photo_urls:
                        logger.warning("Empty photo_urls list after parsing")

                        # Если в БД не сохранены фотографии, но флаг установлен,
                        # попробуем получить фотографии напрямую из API
                        try:
                            # Получаем API-ключ пользователя
                            user = session.get(UserSettings, user_id)
                            if user and user.wb_api_key:
                                # Инициализируем API
                                wb_api = WildberriesAPI(user.wb_api_key)

                                # Получаем отзыв напрямую из API
                                api_review = await wb_api.get_review_by_id(review_id)

                                if api_review:
                                    # Извлекаем URL фотографий
                                    photo_urls = wb_api._extract_photo_links(api_review)

                                    if photo_urls:
                                        logger.info(f"Retrieved {len(photo_urls)} photos from API")

                                        # Обновляем информацию в базе данных
                                        review.photo_urls = json.dumps(photo_urls)
                                        session.commit()
                                        logger.info(f"Updated photo_urls in DB for review {review_id}")
                                        has_photos = True
                        except Exception as api_error:
                            logger.error(f"Error getting photos from API: {api_error}")

                except Exception as e:
                    logger.error(f"Error parsing photo URLs: {e}")
                    has_photos = False

            # Создаем клавиатуру с вариантами действий
            builder = InlineKeyboardBuilder()

            # Добавляем кнопку "Показать все фото", если есть больше одной фотографии
            if has_photos and len(photo_urls) > 1:
                builder.button(text=f"📷 Показать все фото ({len(photo_urls)})",
                               callback_data=f"show_photos_{review_id}")

            builder.button(text="✍️ Ручной ответ", callback_data=f"manual_{review_id}")
            builder.button(text="🤖 Автогенерация", callback_data=f"generate_{review_id}")
            builder.button(text="◀️ Назад", callback_data="pending_reviews")
            builder.adjust(1)  # Одна кнопка в строке

            # Удаляем предыдущее сообщение, если это callback
            try:
                await callback.message.delete()
                logger.info("Previous message deleted")
            except Exception as e:
                logger.error(f"Error deleting previous message: {e}")

            # Если нет фотографий, отправляем только текст
            if not has_photos or not photo_urls:
                logger.info("No photos to display, sending text only")
                await callback.message.answer(
                    review_text,
                    reply_markup=builder.as_markup(),
                    parse_mode="Markdown"
                )
            else:
                # Если есть фотографии, отправляем первую с текстом отзыва в подписи
                try:
                    logger.info(f"Sending first photo with caption: {photo_urls[0]}")

                    # Проверяем, не превышает ли текст максимальную длину подписи
                    max_caption_length = 1024  # Максимальная длина подписи в Telegram

                    if len(review_text) > max_caption_length:
                        # Сокращаем текст, если он слишком длинный
                        review_text = review_text[:max_caption_length - 100] + "...\n\n(текст сокращен)"

                    # Отправляем первую фотографию с текстом отзыва
                    sent_message = await callback.message.answer_photo(
                        photo=photo_urls[0],
                        caption=review_text,
                        reply_markup=builder.as_markup(),
                        parse_mode="Markdown"
                    )
                    logger.info(f"Photo with caption sent: message_id={sent_message.message_id}")

                except Exception as photo_error:
                    logger.error(f"Error sending photo with caption: {photo_error}", exc_info=True)
                    # В случае ошибки отправляем только текст
                    await callback.message.answer(
                        f"{review_text}\n\n_Ошибка загрузки фотографии_",
                        reply_markup=builder.as_markup(),
                        parse_mode="Markdown"
                    )

            # Сохраняем ID отзыва в состоянии
            await state.update_data(review_id=review_id, regeneration_count=0,
                                    has_photo=has_photos and bool(photo_urls))
    except Exception as e:
        logger.error(f"Error in review_detail_handler: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка при загрузке отзыва", show_alert=True)
        try:
            await callback.message.answer(
                "❌ Произошла ошибка при загрузке отзыва. Попробуйте ещё раз.",
                reply_markup=back_button_auto3()
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("show_photos_"))
async def show_all_photos_handler(callback: types.CallbackQuery, state: FSMContext):
    """
    Обработчик для отображения всех фотографий отзыва в альбоме

    Args:
        callback: Колбэк от кнопки
        state: Состояние FSM
    """
    try:
        # Извлекаем ID отзыва из callback_data
        review_id = callback.data.split("_")[2]
        user_id = callback.from_user.id

        logger.info(f"Showing all photos for review {review_id}")

        # Получаем данные отзыва из БД
        with Session() as session:
            review = session.query(Review).filter_by(
                source_api_id=review_id,
                user_id=user_id
            ).first()

            if not review or not review.photo_urls:
                await callback.answer("Фотографии не найдены", show_alert=True)
                return

            # Парсим JSON-строку с URL фотографий
            try:
                photo_urls = json.loads(review.photo_urls)
                if not photo_urls:
                    await callback.answer("Фотографии не найдены", show_alert=True)
                    return

                logger.info(f"Preparing to show {len(photo_urls)} photos")

                # Создаем медиагруппу из всех фотографий
                media_group = []
                for i, photo_url in enumerate(photo_urls):
                    try:
                        caption = f"Фото {i + 1}/{len(photo_urls)}" if i == 0 else ""
                        media_group.append(types.InputMediaPhoto(
                            media=photo_url,
                            caption=caption
                        ))
                    except Exception as e:
                        logger.error(f"Error adding photo to media group: {e}", exc_info=True)

                if not media_group:
                    await callback.answer("Ошибка подготовки фотографий", show_alert=True)
                    return

                # Отправляем альбом с фотографиями
                await callback.bot.send_media_group(
                    chat_id=callback.message.chat.id,
                    media=media_group
                )

                # Отправляем кнопку "Назад к отзыву"
                await callback.message.answer(
                    "Фотографии к отзыву:",
                    reply_markup=InlineKeyboardBuilder()
                    .button(text="◀️ Назад к отзыву", callback_data=f"review_{review_id}")
                    .as_markup()
                )

            except Exception as e:
                logger.error(f"Error parsing or sending photos: {e}", exc_info=True)
                await callback.answer("Ошибка загрузки фотографий", show_alert=True)

    except Exception as e:
        logger.error(f"Error in show_all_photos_handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка при загрузке фотографий", show_alert=True)


@router.callback_query(F.data.startswith("manual_"))
async def start_manual_reply(callback: types.CallbackQuery, state: FSMContext):
    """
    Обработчик для начала ручного ответа на отзыв

    Args:
        callback: Колбэк от кнопки
        state: Состояние FSM
    """
    try:
        # Извлекаем ID отзыва из callback_data
        review_id = callback.data.split("_")[1]

        # Сохраняем ID отзыва в состоянии
        await state.update_data(review_id=review_id)

        # Создаем клавиатуру с кнопкой возврата
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад", callback_data=f"review_{review_id}")

        # Запрашиваем текст ответа
        await callback.message.edit_text(
            "✍️ *Напишите ваш ответ на отзыв:*\n\n"
            "Отправьте текстовое сообщение с вашим ответом.",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )

        # Устанавливаем состояние ожидания ответа
        await state.set_state(ReviewState.waiting_for_custom_reply)

    except Exception as e:
        logger.error(f"Error in start_manual_reply: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при запуске ручного ответа", show_alert=True)


@router.callback_query(F.data.startswith("generate_"))
async def start_generation_flow(callback: types.CallbackQuery, state: FSMContext):
    """
    Обработчик для начала процесса автогенерации ответа

    Args:
        callback: Колбэк от кнопки
        state: Состояние FSM
    """
    try:
        # Извлекаем ID отзыва из callback_data
        review_id = callback.data.split("_")[1]

        # Сохраняем ID отзыва в состоянии
        await state.update_data(review_id=review_id)

        # Создаем клавиатуру с кнопкой возврата
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад", callback_data=f"review_{review_id}")

        # Запрашиваем аргументы для ответа
        await callback.message.edit_text(
            "📝 *Введите аргументы для ответа:*\n\n"
            "Укажите через запятую ключевые моменты, которые хотите включить в ответ.\n"
            "Например: _благодарность за выбор, индивидуальный подход, качество товаров_",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )

        # Устанавливаем состояние ожидания аргументов
        await state.set_state(ReviewState.waiting_for_arguments)

    except Exception as e:
        logger.error(f"Error in start_generation_flow: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при запуске генерации", show_alert=True)


@router.message(ReviewState.waiting_for_arguments)
async def process_review_arguments(message: types.Message, state: FSMContext):
    """
    Обработчик для приема аргументов от пользователя

    Args:
        message: Сообщение с аргументами
        state: Состояние FSM
    """
    try:
        # Разбиваем сообщение на аргументы
        arguments = [arg.strip() for arg in message.text.split(",") if arg.strip()]

        # Сохраняем аргументы в состоянии
        await state.update_data(arguments=arguments)

        # Получаем ID отзыва из состояния
        data = await state.get_data()
        review_id = data.get("review_id")

        # Создаем клавиатуру для выбора действий
        builder = InlineKeyboardBuilder()
        builder.button(text="⏭ Пропустить", callback_data="skip_solution")
        builder.button(text="◀️ Назад", callback_data=f"review_{review_id}")
        builder.adjust(1)

        # Запрашиваем решение проблемы
        await message.answer(
            "💡 *Хотите предложить решение проблемы?*\n\n"
            "Опишите, как вы планируете решить проблему клиента, если она есть, "
            "или нажмите 'Пропустить', если в этом нет необходимости.",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )

        # Устанавливаем состояние ожидания решения
        await state.set_state(ReviewState.waiting_for_solution)

    except Exception as e:
        logger.error(f"Error in process_review_arguments: {e}", exc_info=True)

        # Получаем ID отзыва из состояния для кнопки возврата
        data = await state.get_data()
        review_id = data.get("review_id")

        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад", callback_data=f"review_{review_id}")

        await message.answer(
            "❌ Произошла ошибка. Попробуйте ещё раз.",
            reply_markup=builder.as_markup()
        )


@router.callback_query(F.data == "skip_solution", ReviewState.waiting_for_solution)
async def handle_skip_solution(callback: types.CallbackQuery, state: FSMContext):
    """
    Обработчик для пропуска ввода решения

    Args:
        callback: Колбэк от кнопки
        state: Состояние FSM
    """
    try:
        # Устанавливаем решение как None
        await state.update_data(solution=None)

        # Запускаем процесс генерации
        await process_generation(callback, state)

    except Exception as e:
        logger.error(f"Error in handle_skip_solution: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.message(ReviewState.waiting_for_solution)
async def process_solution(message: types.Message, state: FSMContext):
    """
    Обработчик для приема решения от пользователя

    Args:
        message: Сообщение с решением
        state: Состояние FSM
    """
    try:
        # Сохраняем решение в состоянии
        await state.update_data(solution=message.text)

        # Запускаем процесс генерации
        await process_generation(message, state)

    except Exception as e:
        logger.error(f"Error in process_solution: {e}", exc_info=True)

        # Получаем ID отзыва из состояния для кнопки возврата
        data = await state.get_data()
        review_id = data.get("review_id")

        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад", callback_data=f"review_{review_id}")

        await message.answer(
            "❌ Произошла ошибка. Попробуйте ещё раз.",
            reply_markup=builder.as_markup()
        )


async def process_generation(source: Union[types.Message, types.CallbackQuery], state: FSMContext):
    """
    Обрабатывает генерацию ответа на отзыв

    Args:
        source: Источник события (сообщение или колбэк)
        state: Состояние FSM
    """
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        is_regenerate = data.get("is_regenerate", False)
        review_id = data.get("review_id")

        if not review_id:
            raise ValueError("Review ID not found in state")

        # Получаем данные пользователя и отзыва
        with Session() as session:
            user_id = source.from_user.id
            user = session.get(UserSettings, user_id)

            if not user:
                raise ValueError(f"User {user_id} not found")

            # Получаем отзыв из базы данных
            review = session.query(Review).filter_by(
                source_api_id=review_id,
                user_id=user_id
            ).first()

            if not review:
                raise ValueError(f"Review {review_id} not found for user {user_id}")

            # Преобразуем отзыв в словарь для совместимости с build_prompt
            review_dict = {
                "id": review.source_api_id,
                "stars": review.stars,
                "comment": review.comment,
                "pros": review.pros,
                "cons": review.cons,
                "photo": bool(review.photo_url)
            }

            # Генерация промпта
            prompt = build_prompt(
                review=review_dict,
                user=user,
                arguments=data.get("arguments", []),
                solution=data.get("solution")
            )

            # Добавляем перефразирование только при регенерации
            if is_regenerate:
                prompt += "\n\nПопробуй написать другими словами:"
                await state.update_data(is_regenerate=False)

            # Генерируем ответ
            generated_reply = generate_reply(prompt)
            await state.update_data(generated_reply=generated_reply)

            # Создаем клавиатуру с вариантами действий
            builder = InlineKeyboardBuilder()
            builder.button(text="🔄 Сгенерировать заново", callback_data="regenerate")
            builder.button(text="✍️ Ручной ответ", callback_data="write_own")
            builder.button(text="✅ Отправить", callback_data="send_reply")
            builder.button(text="◀️ Назад", callback_data=f"review_{review_id}")
            builder.adjust(1)

            # Отправляем сгенерированный ответ
            if isinstance(source, types.Message):
                await source.answer(
                    f"🤖 *Сгенерированный ответ:*\n\n{generated_reply}",
                    reply_markup=builder.as_markup(),
                    parse_mode="Markdown"
                )
            else:  # CallbackQuery
                await source.message.edit_text(
                    f"🤖 *Сгенерированный ответ:*\n\n{generated_reply}",
                    reply_markup=builder.as_markup(),
                    parse_mode="Markdown"
                )

    except Exception as e:
        logger.error(f"Error in process_generation: {e}", exc_info=True)
        error_msg = "❌ Произошла ошибка при генерации ответа. Попробуйте ещё раз."

        # Получаем ID отзыва из состояния для кнопки возврата
        try:
            data = await state.get_data()
            review_id = data.get("review_id")

            builder = InlineKeyboardBuilder()
            builder.button(text="◀️ Назад", callback_data=f"review_{review_id}")

            if isinstance(source, types.Message):
                await source.answer(error_msg, reply_markup=builder.as_markup())
            else:  # CallbackQuery
                await source.message.edit_text(error_msg, reply_markup=builder.as_markup())
        except Exception:
            # Базовое сообщение об ошибке, если не удалось сформировать клавиатуру
            if isinstance(source, types.Message):
                await source.answer(error_msg)
            else:  # CallbackQuery
                await source.message.edit_text(error_msg)


@router.message(ReviewState.waiting_for_custom_reply)
async def process_custom_reply(message: types.Message, state: FSMContext):
    """
    Обработчик для приема пользовательского ответа

    Args:
        message: Сообщение с ответом
        state: Состояние FSM
    """
    try:
        # Проверяем наличие текста
        if not message.text:
            await message.answer("❌ Пожалуйста, введите текстовый ответ")
            return

        # Получаем ID отзыва из состояния
        data = await state.get_data()
        review_id = data.get("review_id")

        if not review_id:
            await message.answer("❌ Произошла ошибка: отзыв не найден")
            return

        # Сохраняем пользовательский ответ
        await state.update_data(generated_reply=message.text)

        # Создаем клавиатуру для подтверждения отправки
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Отправить ответ", callback_data="send_reply")
        builder.button(text="◀️ Назад", callback_data=f"review_{review_id}")
        builder.adjust(1)

        # Показываем предпросмотр ответа
        await message.answer(
            f"📝 *Ваш ответ:*\n\n{message.text}\n\n"
            "Нажмите 'Отправить ответ' для отправки или 'Назад' для возврата.",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error in process_custom_reply: {e}", exc_info=True)

        # Получаем ID отзыва из состояния для кнопки возврата
        data = await state.get_data()
        review_id = data.get("review_id", "")

        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад", callback_data=f"review_{review_id}")

        await message.answer(
            "❌ Произошла ошибка. Попробуйте ещё раз.",
            reply_markup=builder.as_markup()
        )


@router.callback_query(F.data == "write_own")
async def write_own_callback(callback: types.CallbackQuery, state: FSMContext):
    """
    Обработчик для перехода к написанию собственного ответа

    Args:
        callback: Колбэк от кнопки
        state: Состояние FSM
    """
    try:
        # Получаем ID отзыва из состояния
        data = await state.get_data()
        review_id = data.get("review_id")

        # Создаем клавиатуру с кнопкой возврата
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад", callback_data=f"review_{review_id}")

        # Запрашиваем пользовательский ответ
        await callback.message.edit_text(
            "✍️ *Напишите ваш собственный ответ:*\n\n"
            "Отправьте текстовое сообщение с вашим ответом.",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )

        # Устанавливаем состояние ожидания ответа
        await state.set_state(ReviewState.waiting_for_custom_reply)

    except Exception as e:
        logger.error(f"Error in write_own_callback: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "regenerate")
async def regenerate_reply(callback: types.CallbackQuery, state: FSMContext):
    """
    Обработчик для повторной генерации ответа

    Args:
        callback: Колбэк от кнопки
        state: Состояние FSM
    """
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        count = data.get("regeneration_count", 0)

        # Проверяем лимит регенераций
        if count >= 3:
            await callback.answer(
                "Лимит генерации достигнут (3 раза). Используйте ручной ответ.",
                show_alert=True
            )
            return

        # Увеличиваем счетчик регенераций и устанавливаем флаг
        await state.update_data(
            regeneration_count=count + 1,
            is_regenerate=True
        )

        # Запускаем процесс генерации
        await process_generation(callback, state)

    except Exception as e:
        logger.error(f"Error in regenerate_reply: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка при генерации", show_alert=True)


@router.callback_query(F.data == "send_reply")
async def send_reply_handler(callback: types.CallbackQuery, state: FSMContext):
    """
    Обработчик для отправки ответа

    Args:
        callback: Колбэк от кнопки
        state: Состояние FSM
    """
    try:
        # Показываем индикатор загрузки
        await callback.answer("Отправка ответа...")

        # Получаем данные из состояния
        data = await state.get_data()
        review_id = data.get("review_id")
        reply_text = data.get("generated_reply")

        # Проверяем наличие необходимых данных
        if not review_id:
            await callback.message.edit_text(
                "❌ Ошибка: ID отзыва не найден",
                reply_markup=back_button_auto3()
            )
            return

        if not reply_text:
            await callback.message.edit_text(
                "❌ Ошибка: текст ответа не найден",
                reply_markup=back_button_auto3()
            )
            return

        # Отправляем ответ через API
        success = await send_review_reply(
            feedback_id=review_id,
            text=reply_text,
            user_id=callback.from_user.id
        )

        if success:
            # Очищаем состояние
            await state.clear()

            # Показываем сообщение об успешной отправке
            await callback.message.edit_text(
                "✅ Ответ успешно отправлен!\n\n"
                "Хотите просмотреть другие отзывы?",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="📋 Список отзывов", callback_data="pending_reviews")
                    .button(text="🏠 Главное меню", callback_data="start")
                    .adjust(1)
                    .as_markup()
            )
        else:
            # Показываем сообщение об ошибке
            await callback.message.edit_text(
                "❌ Ошибка при отправке ответа. Попробуйте ещё раз.",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔄 Повторить", callback_data="send_reply")
                    .button(text="◀️ Назад", callback_data=f"review_{review_id}")
                    .adjust(1)
                    .as_markup()
            )

    except Exception as e:
        logger.error(f"Error in send_reply_handler: {e}", exc_info=True)

        # Получаем ID отзыва из состояния для кнопки возврата
        try:
            data = await state.get_data()
            review_id = data.get("review_id", "")

            await callback.message.edit_text(
                "❌ Произошла ошибка при отправке ответа. Попробуйте ещё раз.",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="🔄 Повторить", callback_data="send_reply")
                    .button(text="◀️ Назад", callback_data=f"review_{review_id}")
                    .adjust(1)
                    .as_markup()
            )
        except Exception:
            await callback.answer("❌ Произошла ошибка при отправке ответа", show_alert=True)


@router.callback_query(F.data == "back_to_reviews")
async def back_to_reviews_handler(callback: types.CallbackQuery, state: FSMContext):
    """
    Обработчик для возврата к списку отзывов

    Args:
        callback: Колбэк от кнопки
        state: Состояние FSM
    """
    try:
        # Очищаем состояние
        await state.clear()

        # Вызываем обработчик списка отзывов
        await reviews_list_handler(callback, state)

    except Exception as e:
        logger.error(f"Error in back_to_reviews_handler: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка", show_alert=True)

# ============ Запуск фоновой задачи ============

async def on_startup(dp):
    """
    Функция для запуска фоновых задач при старте бота

    Args:
        dp: Диспетчер
    """
    # Создаем планировщик задач
    scheduler = AsyncIOScheduler()

    # Добавляем задачу проверки отзывов каждые 5 минут
    scheduler.add_job(
        check_new_reviews,
        'interval',
        minutes=5,
        args=(dp.bot,),
        kwargs={},
        id='check_reviews',
        replace_existing=True
    )

    # Запускаем планировщик
    scheduler.start()
    logger.info("Review check scheduler started")