# update_photos.py
import asyncio
import logging
import json
import sqlite3
import sys
import os

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Добавляем текущую директорию в путь для импорта
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Импортируем необходимые модули
from models import UserSettings, Session
from utils.wb_api import WildberriesAPI


async def update_photos_in_database():
    """
    Обновляет фотографии для существующих отзывов
    """
    try:
        logger.info("Starting photo update script")

        # Получаем список пользователей с API ключами
        with Session() as session:
            users = session.query(UserSettings).filter(UserSettings.wb_api_key != None).all()

            if not users:
                logger.error("No users with API keys found")
                return

            logger.info(f"Found {len(users)} users with API keys")

            # Для каждого пользователя
            for user in users:
                try:
                    # Создаем экземпляр API
                    api = WildberriesAPI(user.wb_api_key)

                    # Получаем отзывы из API
                    reviews_1 = await api.get_unanswered_reviews(is_answered=False)
                    reviews_2 = await api.get_unanswered_reviews(is_answered=True)
                    reviews = reviews_1 + reviews_2

                    logger.info(f"Retrieved {len(reviews)} reviews for user {user.user_id}")

                    # Подключаемся к базе данных напрямую для обновления
                    conn = sqlite3.connect('bot.db')
                    cursor = conn.cursor()

                    # Обновляем каждый отзыв
                    update_count = 0
                    for review in reviews:
                        try:
                            review_id = str(review.get("id", ""))

                            # Извлекаем URL фотографий, учитывая специфический формат API
                            photo_links = []
                            raw_photo_links = review.get("photoLinks", [])

                            # Если это список объектов с полями fullSize и miniSize
                            if isinstance(raw_photo_links, list) and raw_photo_links and isinstance(raw_photo_links[0],
                                                                                                    dict):
                                for photo in raw_photo_links:
                                    if "fullSize" in photo:
                                        photo_links.append(photo["fullSize"])
                                    elif "miniSize" in photo:
                                        photo_links.append(photo["miniSize"])

                            if photo_links:
                                # Сохраняем список URL как JSON строку
                                photo_urls_json = json.dumps(photo_links)

                                # Обновляем запись в БД
                                cursor.execute(
                                    "UPDATE reviews SET photo_urls = ?, photo_url = ? WHERE source_api_id = ? AND user_id = ?",
                                    (photo_urls_json, True, review_id, user.user_id)
                                )

                                if cursor.rowcount > 0:
                                    update_count += 1
                                    logger.info(f"Updated photos for review {review_id}: {photo_links}")

                            # Обновляем информацию о товаре
                            product_details = review.get("productDetails", {})
                            if product_details:
                                # Артикул продавца
                                supplier_article = product_details.get("supplierArticle", "")
                                # Название товара
                                product_name = product_details.get("productName", "")
                                # Категория товара (тип)
                                subject_name = review.get("subjectName", "")

                                # Обновляем БД
                                cursor.execute(
                                    """
                                    UPDATE reviews 
                                    SET supplier_article = ?, product_name = ?, subject_name = ?
                                    WHERE source_api_id = ? AND user_id = ?
                                    """,
                                    (supplier_article, product_name, subject_name, review_id, user.user_id)
                                )

                        except Exception as review_error:
                            logger.error(f"Error updating review {review.get('id', '')}: {review_error}")

                    # Сохраняем изменения
                    conn.commit()
                    conn.close()

                    logger.info(f"Updated {update_count} reviews for user {user.user_id}")

                except Exception as user_error:
                    logger.error(f"Error processing user {user.user_id}: {user_error}")

        logger.info("Photo update completed")

    except Exception as e:
        logger.error(f"Database update error: {str(e)}", exc_info=True)
        return False


# Запускаем асинхронную функцию
if __name__ == "__main__":
    asyncio.run(update_photos_in_database())