import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import Config
from utils import pagination, prompts
from handlers import (
    start,
    consultation,
    tables,
    settings,
    signatures,
    reviews,
    auto_reply,
    auto_reply_five_stars
)

async def main():
    # Настройка логов
    logging.basicConfig(
        level=logging.INFO,
        format=Config.LOG_FORMAT
    )

    # Инициализация бота
    bot = Bot(token=Config.API_TOKEN)
    dp = Dispatcher()

    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(consultation.router)
    dp.include_router(tables.router)
    dp.include_router(auto_reply.router)
    dp.include_router(settings.router)
    dp.include_router(signatures.router)
    dp.include_router(reviews.router)
    dp.include_router(auto_reply_five_stars.router)

    # Запуск поллинга
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())