"""Основной файл бота"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from sqlalchemy.ext.asyncio import async_sessionmaker

from config import BOT_TOKEN, DATABASE_URL
from database import init_db
from handlers import router
from middlewares import DatabaseMiddleware

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


async def set_commands(bot: Bot):
    """Установка команд бота"""
    commands = [
        BotCommand(command="start", description="🚀 Запустить бота"),
        BotCommand(command="menu", description="📋 Главное меню"),
        BotCommand(command="bal", description="💵 Проверить баланс"),
        BotCommand(command="inv", description="🎒 Инвентарь"),
        BotCommand(command="lvl", description="📈 Уровень"),
        BotCommand(command="limit", description="💸 Лимит переводов"),
    ]
    await bot.set_my_commands(commands)
    logger.info("Команды бота установлены")


async def main():
    """Основная функция"""
    # Проверка токена
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден! Добавьте его в .env файл")
        return
    
    # Инициализация бота и диспетчера
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Инициализация базы данных
    async_session = await init_db(DATABASE_URL)
    logger.info("✅ База данных инициализирована")
    
    # Добавление middleware
    dp.update.middleware(DatabaseMiddleware(async_session))
    
    # Регистрация роутеров
    dp.include_router(router)
    
    # Установка команд
    await set_commands(bot)
    
    # Запуск поллинга
    logger.info("🤖 Бот запущен...")
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
    finally:
        await bot.close()
        logger.info("✅ Бот закрыт")


if __name__ == "__main__":
    asyncio.run(main())
