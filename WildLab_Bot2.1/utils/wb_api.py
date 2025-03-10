import ssl
import aiohttp
from models import UserSettings, Session
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class WildberriesAPI:
    def __init__(self, api_key: str):
        self.base_url = "https://feedbacks-api.wb.ru/api/v1"
        self.headers = {
            "Authorization": api_key,
            "Content-Type": "application/json"
        }
        # Создаем кастомный SSL-контекст
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    async def _make_request(self, method: str, endpoint: str, params: dict = None) -> Dict[str, Any]:
        """Универсальный метод для выполнения запросов с отключенной SSL-проверкой"""
        url = f"{self.base_url}{endpoint}"
        try:
            # Используем кастомный SSL-контекст
            connector = aiohttp.TCPConnector(ssl=self.ssl_context)

            async with aiohttp.ClientSession(connector=connector) as session:
                # Обработка параметров
                processed_params = {}
                for key, value in (params or {}).items():
                    if value is None:
                        continue
                    processed_params[key] = str(value).lower() if isinstance(value, bool) else value

                async with session.request(
                        method=method,
                        url=url,
                        headers=self.headers,
                        params=processed_params
                ) as response:
                    response.raise_for_status()
                    return await response.json()

        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            return {}

    async def get_unanswered_reviews(self) -> List[Dict[str, Any]]:
        """Получение непросмотренных отзывов"""
        try:
            response = await self._make_request(
                "GET",
                "/feedbacks",
                params={
                    "isAnswered": False,
                    "take": 5000,
                    "skip": 0,
                    "order": "dateDesc"
                }
            )
            return response.get("data", {}).get("feedbacks", [])

        except Exception as e:
            logger.error(f"Get reviews error: {str(e)}")
            return []


async def fetch_reviews(user_id: int) -> List[Dict[str, Any]]:
    """Функция для получения отзывов с отключенной SSL-проверкой"""
    try:
        with Session() as session:
            user = session.get(UserSettings, user_id)
            if not user or not user.wb_api_key:
                return []

            api = WildberriesAPI(user.wb_api_key)
            return await api.get_unanswered_reviews()

    except Exception as e:
        logger.error(f"Fetch error: {str(e)}")
        return []