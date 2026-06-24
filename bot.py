"""Основной файл бота"""
import asyncio
import logging
import random
import json
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select

from config import BOT_TOKEN, DATABASE_URL, BASE_MINING_TIME, PLASMA_CHANCE, CASE_CHANCE, CASE_TYPES
from database import init_db, MiningSession, get_or_create_user
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


def calculate_power(pickaxe: float, booster: float) -> float:
    """Расчёт мощности кирки"""
    return pickaxe * booster


async def mining_progress_task():
    """Фоновая задача: обновление прогресса добычи каждую секунду для всех активных сессий"""
    global _bot_instance, _async_session
    
    # Словарь для отслеживания последней секунды обновления для каждой сессии
    # {user_id: last_second}
    last_update_tracker = {}
    
    while True:
        try:
            await asyncio.sleep(1)  # Обновление каждую секунду
            
            if not _async_session:
                continue
            
            async with _async_session() as session:
                now = datetime.utcnow()
                
                # Найти все активные сессии
                result = await session.execute(
                    select(MiningSession).where(
                        MiningSession.is_active == True,
                        MiningSession.end_time > now
                    )
                )
                active_sessions = result.scalars().all()
                
                for ms in active_sessions:
                    user_id = ms.user_id
                    
                    # Получаем пользователя для мощности и шансов
                    user = await get_or_create_user(session, user_id)
                    
                    # Проверяем, прошла ли секунда с последнего обновления
                    current_second = int(now.timestamp())
                    last_second = last_update_tracker.get(user_id, 0)
                    
                    if current_second <= last_second:
                        continue  # Ещё не прошла секунда
                    
                    last_update_tracker[user_id] = current_second
                    
                    # Мощность кирки с учётом бонуса за подписку
                    mining_bonus = user.mining_bonus or 1.0
                    power = calculate_power(user.pickaxe_power or 1.0, user.booster_power or 1.0, mining_bonus)
                    
                    # 1 удар = 1 секунда
                    ms.hits = (ms.hits or 0) + 1
                    
                    # Руда = удары × мощность (пересчитываем накопительно)
                    ms.ores_dug = int(ms.hits * power)
                    
                    # Плазма с шансом 5%
                    if random.random() * 100 < (user.plasma_chance or PLASMA_CHANCE):
                        ms.plasma_dug = (ms.plasma_dug or 0) + 1
                    
                    # Кейсы с шансом 3%
                    existing_cases = json.loads(ms.cases_list) if ms.cases_list else []
                    if random.random() * 100 < CASE_CHANCE:
                        existing_cases.append(random.choice(CASE_TYPES))
                        ms.cases_list = json.dumps(existing_cases)
                        ms.cases_found = len(existing_cases)
                    
                    ms.last_update = now
                
                await session.commit()
                        
        except Exception as e:
            logger.error(f"❌ Ошибка в mining_progress_task: {e}")
            await asyncio.sleep(1)


async def mining_timer_task():
    """Фоновая задача: проверка завершённых сессий и отправка уведомлений"""
    global _bot_instance, _async_session
    
    # Отслеживаем уже обработанные сессии, чтобы не отправлять уведомление дважды
    notified_sessions = set()
    
    while True:
        try:
            await asyncio.sleep(2)  # Проверка каждые 2 секунды
            
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
                    if ms.user_id in notified_sessions:
                        continue  # Уже отправили уведомление
                    
                    try:
                        # Останавливаем сессию
                        ms.is_active = False
                        ms.notification_sent = True
                        
                        # Получаем пользователя для обновления состояния
                        user = await get_or_create_user(session, ms.user_id)
                        
                        # Сохраняем в сессию пользователя для последующего сбора
                        user.session_hits = ms.hits or 0
                        user.session_ores = ms.ores_dug or 0
                        user.session_plasma = ms.plasma_dug or 0
                        user.session_cases = ms.cases_found or 0
                        user.is_mining = False
                        
                        await session.commit()
                        
                        await send_mining_finished_notification(_bot_instance, session, ms)
                        notified_sessions.add(ms.user_id)
                        logger.info(f"✅ Уведомление отправлено пользователю {ms.user_id}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки уведомления для {ms.user_id}: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Ошибка в mining_timer_task: {e}")
            await asyncio.sleep(5)


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
    
    # Запуск фоновых задач
    progress_task = asyncio.create_task(mining_progress_task())
    timer_task = asyncio.create_task(mining_timer_task())
    logger.info("⏱️ Фоновые задачи добычи запущены")
    
    # Запуск поллинга
    logger.info("🤖 Бот запущен...")
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
    finally:
        progress_task.cancel()
        timer_task.cancel()
        await bot.close()
        logger.info("✅ Бот закрыт")


if __name__ == "__main__":
    asyncio.run(main())
