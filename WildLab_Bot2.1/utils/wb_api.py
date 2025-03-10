import ssl
import json
import aiohttp
import asyncio
from models import UserSettings, Session
import logging
from typing import Dict, Any, List, Optional, Union

logger = logging.getLogger(__name__)


class WildberriesAPI:
    """
    Класс для работы с API Wildberries для управления отзывами

    Документация API: https://dev.wildberries.ru/openapi/user-communication
    """

    def __init__(self, api_key: str):
        # Базовый URL для API отзывов
        self.base_url = "https://feedbacks-api.wb.ru/api/v1"

        # Заголовки для запросов
        self.headers = {
            "Authorization": api_key,
            "Content-Type": "application/json"
        }

        # Создаем SSL-контекст с отключенной проверкой сертификатов
        # ВАЖНО: В production использовании рекомендуется включить проверку сертификатов
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    async def _make_request(
            self,
            method: str,
            endpoint: str,
            params: Dict[str, Any] = None,
            json_data: Dict[str, Any] = None,
            retry_count: int = 3
    ) -> Dict[str, Any]:
        """
        Универсальный метод для выполнения запросов к API с обработкой ошибок и повторными попытками

        Args:
            method: HTTP метод (GET, POST, PUT, DELETE)
            endpoint: Эндпоинт API (без базового URL)
            params: URL параметры запроса
            json_data: Данные для отправки в формате JSON
            retry_count: Количество повторных попыток при ошибках

        Returns:
            Dict[str, Any]: Ответ API в формате JSON или пустой словарь в случае ошибки
        """
        url = f"{self.base_url}{endpoint}"

        # Обработка параметров запроса
        request_params = {}
        if params:
            for key, value in params.items():
                if value is None:
                    continue
                # Преобразуем булевы значения в строки "true"/"false" для API
                if isinstance(value, bool):
                    request_params[key] = str(value).lower()
                else:
                    request_params[key] = value

        # Счетчик попыток
        attempts = 0
        last_error = None

        while attempts < retry_count:
            attempts += 1
            try:
                # Используем кастомный SSL-контекст с отключенной проверкой сертификатов
                connector = aiohttp.TCPConnector(ssl=self.ssl_context)

                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.request(
                            method=method,
                            url=url,
                            headers=self.headers,
                            params=request_params,
                            json=json_data,
                            timeout=30  # Таймаут запроса 30 секунд
                    ) as response:
                        # Получаем текст ответа для логгирования
                        response_text = await response.text()

                        # Проверяем код ответа
                        if response.status == 429:  # Rate limit
                            retry_after = int(response.headers.get("Retry-After", 5))
                            logger.warning(f"Rate limit reached. Retrying after {retry_after} seconds...")
                            await asyncio.sleep(retry_after)
                            continue

                        # Пробуем прочитать JSON ответ
                        try:
                            # Сбрасываем указатель на начало содержимого ответа
                            response_json = json.loads(response_text)
                        except json.JSONDecodeError:
                            logger.error(f"Invalid JSON response: {response_text}")
                            return {"error": {"message": f"Invalid JSON response (Status: {response.status})"}}

                        # Проверяем наличие ошибок в ответе API по коду статуса
                        if response.status >= 400:
                            error_info = f"API error: Status {response.status}, Response: {response_text}"
                            logger.error(error_info)

                            # Если ошибка связана с авторизацией, не пытаемся повторить запрос
                            if response.status in (401, 403):
                                return {"error": {"message": f"Authentication error (Status: {response.status})"}}

                            # Для других ошибок пробуем повторить запрос
                            if attempts < retry_count:
                                # Увеличиваем задержку с каждой попыткой (экспоненциальная задержка)
                                await asyncio.sleep(2 ** attempts)
                                continue
                            else:
                                return {"error": {
                                    "message": f"API error after {retry_count} retries (Status: {response.status})"}}

                        # Проверяем формат ответа
                        if not isinstance(response_json, dict):
                            logger.warning(f"Unexpected response format: {response_json}")
                            return {"data": response_json}

                        return response_json

            except asyncio.TimeoutError:
                logger.warning(f"Request timeout ({attempts}/{retry_count})")
                last_error = "Request timeout"
                # Увеличиваем задержку перед повторной попыткой
                await asyncio.sleep(2 ** attempts)

            except aiohttp.ClientError as e:
                logger.error(f"HTTP client error: {str(e)} ({attempts}/{retry_count})")
                last_error = f"HTTP client error: {str(e)}"
                await asyncio.sleep(2 ** attempts)

            except Exception as e:
                logger.error(f"Unexpected error in API request: {str(e)}", exc_info=True)
                last_error = f"Unexpected error: {str(e)}"
                await asyncio.sleep(1)

        # Если все попытки исчерпаны, возвращаем ошибку
        logger.error(f"All {retry_count} retry attempts failed. Last error: {last_error}")
        return {"error": {"message": last_error}}

    def _extract_photo_links(self, review: Dict[str, Any]) -> List[str]:
        """
        Извлекает ссылки на фотографии из отзыва с учетом специфического формата API Wildberries

        Args:
            review: Данные отзыва из API

        Returns:
            List[str]: Список URL фотографий
        """
        try:
            # Получаем значение поля photoLinks
            photo_links = review.get("photoLinks", [])

            # Если поле отсутствует или пустое
            if not photo_links:
                return []

            # Если это список объектов с полями fullSize и miniSize
            if isinstance(photo_links, list) and isinstance(photo_links[0], dict):
                result = []
                for photo in photo_links:
                    # Извлекаем URL полноразмерного изображения
                    if "fullSize" in photo:
                        result.append(photo["fullSize"])
                    elif "miniSize" in photo:
                        result.append(photo["miniSize"])
                return result

            # Если это уже список URL
            if isinstance(photo_links, list) and isinstance(photo_links[0], str):
                return photo_links

            # Если это строка JSON
            if isinstance(photo_links, str):
                try:
                    parsed = json.loads(photo_links)
                    if isinstance(parsed, list):
                        # Рекурсивно обрабатываем распарсенный список
                        return self._extract_photo_links({"photoLinks": parsed})
                except json.JSONDecodeError:
                    return []

            # Если ничего не подошло
            return []

        except Exception as e:
            logger.error(f"Error extracting photo links: {e}")
            return []

    async def get_unanswered_reviews(
            self,
            is_answered: Optional[bool] = False,
            take: int = 5000,
            skip: int = 0,
            nmId: Optional[int] = None,
            order: str = "dateDesc"
    ) -> List[Dict[str, Any]]:
        """
        Получение отзывов с возможностью фильтрации

        Args:
            is_answered: Флаг отвеченных отзывов
            take: Количество запрашиваемых отзывов
            skip: Смещение от начала списка
            nmId: Артикул товара (опционально)
            order: Порядок сортировки (dateDesc - сначала новые, dateAsc - сначала старые)

        Returns:
            List[Dict[str, Any]]: Список отзывов или пустой список в случае ошибки
        """
        try:
            # Формируем параметры запроса - используем строки "true" и "false" вместо булевых значений
            # т.к. API ожидает именно такой формат
            params = {
                "take": take,
                "skip": skip,
                "order": order
            }

            # Добавляем флаг отвеченных отзывов, если он не None
            if is_answered is not None:
                params["isAnswered"] = "true" if is_answered else "false"

            # Добавляем артикул, если он указан
            if nmId is not None:
                params["nmId"] = nmId

            # Выполняем запрос к API
            response = await self._make_request("GET", "/feedbacks", params=params)

            # Проверяем наличие ошибок
            if "error" in response and response["error"]:
                error_text = response.get("errorText", "Unknown error")
                logger.error(f"Error getting reviews: {error_text}")
                return []

            # Извлекаем отзывы из ответа
            feedbacks = response.get("data", {}).get("feedbacks", [])

            # Валидируем результат
            if not isinstance(feedbacks, list):
                logger.error(f"Invalid response format: feedbacks is not a list: {feedbacks}")
                return []

            logger.info(f"Successfully fetched {len(feedbacks)} feedbacks")
            return feedbacks

        except Exception as e:
            logger.error(f"Error fetching reviews: {str(e)}", exc_info=True)
            return []

    async def get_review_by_id(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """
        Получение информации о конкретном отзыве по его ID

        Args:
            feedback_id: ID отзыва

        Returns:
            Optional[Dict[str, Any]]: Данные отзыва или None в случае ошибки
        """
        try:
            logger.info(f"Getting review by ID: {feedback_id}")

            # По логам мы видим, что эндпоинт /feedbacks/{id} не существует или недоступен
            # Поэтому используем только метод получения через список отзывов

            # Получаем все отзывы (отвеченные и неотвеченные)
            all_reviews_1 = await self.get_unanswered_reviews(is_answered=False)
            all_reviews_2 = await self.get_unanswered_reviews(is_answered=True)

            # Объединяем списки
            all_reviews = all_reviews_1 + all_reviews_2

            logger.info(f"Retrieved {len(all_reviews)} total reviews")

            # Ищем нужный отзыв по ID
            for review in all_reviews:
                if str(review.get("id", "")) == feedback_id:
                    logger.info(f"Found review {feedback_id} in the list")
                    return review

            logger.warning(f"Review {feedback_id} not found in any list")
            return None

        except Exception as e:
            logger.error(f"Error fetching review by ID {feedback_id}: {str(e)}", exc_info=True)
            return None

    async def send_reply(self, feedback_id: str, text: str) -> bool:
        """
        Отправка ответа на отзыв

        Args:
            feedback_id: ID отзыва
            text: Текст ответа

        Returns:
            bool: True если ответ успешно отправлен, False в случае ошибки
        """
        try:
            # Проверяем валидность входных данных
            if not feedback_id or not text:
                logger.error("Invalid parameters for send_reply: feedback_id or text is empty")
                return False

            # Согласно документации, для отправки ответа нужно использовать POST запрос
            # с данными в формате JSON
            data = {"text": text}

            # Выполняем запрос к API
            response = await self._make_request(
                "POST",
                f"/feedbacks/{feedback_id}/reply",
                json_data=data
            )

            # Проверяем наличие ошибок
            if "error" in response and response["error"]:
                error_text = response.get("errorText", "Unknown error")
                logger.error(f"Error sending reply: {error_text}")
                return False

            logger.info(f"Successfully sent reply to feedback {feedback_id}")
            return True

        except Exception as e:
            logger.error(f"Error sending reply to feedback {feedback_id}: {str(e)}", exc_info=True)
            return False

    async def get_rating_summary(
            self,
            date_from: Optional[str] = None,
            date_to: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Получение сводной статистики по рейтингам товаров

        Args:
            date_from: Начальная дата в формате YYYY-MM-DD (опционально)
            date_to: Конечная дата в формате YYYY-MM-DD (опционально)

        Returns:
            Optional[Dict[str, Any]]: Сводная статистика или None в случае ошибки
        """
        try:
            # Формируем параметры запроса
            params = {}
            if date_from:
                params["dateFrom"] = date_from
            if date_to:
                params["dateTo"] = date_to

            # Выполняем запрос к API
            response = await self._make_request("GET", "/feedbacks/rating/summary", params=params)

            # Проверяем наличие ошибок
            if "error" in response and response["error"]:
                error_text = response.get("errorText", "Unknown error")
                logger.error(f"Error getting rating summary: {error_text}")
                return None

            # Извлекаем данные
            summary = response.get("data", {})

            return summary

        except Exception as e:
            logger.error(f"Error fetching rating summary: {str(e)}", exc_info=True)
            return None


async def fetch_reviews(user_id: int) -> List[Dict[str, Any]]:
    """
    Функция для получения отзывов через API Wildberries

    Args:
        user_id: ID пользователя

    Returns:
        List[Dict[str, Any]]: Список отзывов или пустой список в случае ошибки
    """
    try:
        with Session() as session:
            user = session.get(UserSettings, user_id)
            if not user or not user.wb_api_key:
                logger.warning(f"User {user_id} has no API key")
                return []

            api = WildberriesAPI(user.wb_api_key)
            return await api.get_unanswered_reviews()

    except Exception as e:
        logger.error(f"Error fetching reviews for user {user_id}: {str(e)}", exc_info=True)
        return []


async def normalize_review_fields(review: Dict[str, Any]) -> Dict[str, Any]:
    """
    Нормализует поля отзыва к единому формату для использования в боте

    Args:
        review: Исходные данные отзыва из API

    Returns:
        Dict[str, Any]: Нормализованные данные отзыва
    """
    try:
        normalized = {}
        api = None  # Создаем экземпляр API только если нужно

        # ID отзыва (обязательное поле)
        normalized["source_api_id"] = str(review.get("id", ""))

        # Звезды (рейтинг)
        normalized["stars"] = int(review.get("productValuation", 0))

        # Текст отзыва (комментарий)
        normalized["comment"] = review.get("text", "")

        # Достоинства (безопасная проверка)
        normalized["pros"] = review.get("pros", "")
        if normalized["pros"] is None:
            normalized["pros"] = ""

        # Недостатки (безопасная проверка)
        normalized["cons"] = review.get("cons", "")
        if normalized["cons"] is None:
            normalized["cons"] = ""

        # Обработка фотографий
        # Создаем экземпляр API для извлечения фотографий
        if api is None:
            api = WildberriesAPI("")  # Пустой API-ключ, т.к. нам нужны только вспомогательные методы

        photo_links = api._extract_photo_links(review)

        if photo_links:
            normalized["photo_urls"] = json.dumps(photo_links)
            normalized["photo_url"] = True
        else:
            normalized["photo_urls"] = "[]"
            normalized["photo_url"] = False

        # Статус ответа (безопасная проверка)
        normalized["is_answered"] = review.get("isAnswered", False)
        if normalized["is_answered"] is None:
            normalized["is_answered"] = False

        # Ответ (если есть) - с безопасной проверкой вложенности
        answer = review.get("answer", {})
        if answer is not None and isinstance(answer, dict):
            normalized["response"] = answer.get("text", "")
        else:
            normalized["response"] = ""

        # Информация о товаре
        product_details = review.get("productDetails", {})
        if product_details is not None and isinstance(product_details, dict):
            normalized["product_name"] = product_details.get("productName", "")
            normalized["product_id"] = str(product_details.get("nmId", ""))
            normalized["supplier_article"] = product_details.get("supplierArticle", "")
        else:
            normalized["product_name"] = ""
            normalized["product_id"] = ""
            normalized["supplier_article"] = ""

        # Тип товара (из корня объекта)
        normalized["subject_name"] = review.get("subjectName", "")

        return normalized

    except Exception as e:
        logger.error(f"Error normalizing review fields: {str(e)}", exc_info=True)
        # Возвращаем минимальный набор полей с безопасными значениями
        return {
            "source_api_id": str(review.get("id", "")) if review else "",
            "comment": str(review.get("text", "")) if review else "",
            "stars": 0,
            "is_answered": False,
            "pros": "",
            "cons": "",
            "photo_url": False,
            "photo_urls": "[]",
            "response": "",
            "product_name": "",
            "product_id": "",
            "supplier_article": "",
            "subject_name": ""
        }