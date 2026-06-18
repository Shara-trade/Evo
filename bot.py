"""Основной файл бота"""
import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select

from config import BOT_TOKEN, DATABASE_URL, BASE_MINING_TIME
from database import init_db, MiningSession
from handlers import router, send_mining_finished_notification
from middlewares import DatabaseMiddleware

# Глобальная ссылка на бота для фоновых задач
_bot_instance: Bot | None = None
_async_session: async_sessionmaker | None = None

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


async def mining_timer_task():
    """Фоновая задача: проверка завершённых сессий и отправка уведомлений"""
    global _bot_instance, _async_session
    
    while True:
        try:
            await asyncio.sleep(5)  # Проверка каждые 5 секунд
            
            if not _bot_instance or not _async_session:
                continue
            
            async with _async_session() as session:
                # Найти активные сессии, у которых время вышло и уведомление ещё не отправлено
                now = datetime.utcnow()
                result = await session.execute(
                    select(MiningSession).where(
                        MiningSession.is_active == True,
                        MiningSession.end_time <= now,
                        MiningSession.notification_sent == False,
                        MiningSession.chat_id != None
                    )
                )
                expired_sessions = result.scalars().all()
                
                for ms in expired_sessions:
                    try:
                        await send_mining_finished_notification(_bot_instance, session, ms)
                        ms.notification_sent = True
                        await session.commit()
                        logger.info(f"✅ Уведомление отправлено пользователю {ms.user_id}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки уведомления для {ms.user_id}: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Ошибка в mining_timer_task: {e}")
            await asyncio.sleep(10)


async def main():
    """Основная функция"""
    global _bot_instance, _async_session
    
    # Проверка токена
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден! Добавьте его в .env файл")
        return
    
    # Инициализация бота и диспетчера
    bot = Bot(token=BOT_TOKEN)
    _bot_instance = bot
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Инициализация базы данных
    _async_session = await init_db(DATABASE_URL)
    logger.info("✅ База данных инициализирована")
    
    # Добавление middleware
    dp.update.middleware(DatabaseMiddleware(_async_session))
    
    # Регистрация роутеров
    dp.include_router(router)
    
    # Установка команд
    await set_commands(bot)
    
    # Запуск фоновой задачи таймера
    timer_task = asyncio.create_task(mining_timer_task())
    logger.info("⏱️ Таймер копания запущен")
    
    # Запуск поллинга
    logger.info("🤖 Бот запущен...")
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
    finally:
        timer_task.cancel()
        await bot.close()
        logger.info("✅ Бот закрыт")


if __name__ == "__main__":
    asyncio.run(main())
