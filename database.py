"""Модуль работы с базой данных"""
from sqlalchemy import Column, Integer, String, BigInteger, Float, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import json

Base = declarative_base()


class User(Base):
    """Таблица пользователей"""
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    
    # Клан
    clan = Column(String, nullable=True)  # Название клана
    
    # Ресурсы
    balance = Column(BigInteger, default=0)
    plasma = Column(BigInteger, default=0)
    level = Column(Integer, default=1)
    experience = Column(Integer, default=0)
    
    # Лимит переводов
    transfer_limit = Column(BigInteger, default=1000)
    received_today = Column(BigInteger, default=0)
    last_reset = Column(DateTime, default=datetime.utcnow)
    
    # Мощность
    pickaxe_power = Column(Float, default=1.0)
    booster_power = Column(Float, default=1.0)
    
    # Шанс плазмы (можно улучшать)
    plasma_chance = Column(Float, default=5.0)  # 5% базовый шанс
    
    # Состояние добычи
    is_mining = Column(Boolean, default=False)
    current_mine = Column(Integer, default=0)
    current_ore = Column(String, nullable=True)  # Текущая руда в сессии
    mining_start = Column(DateTime, nullable=True)
    mining_end = Column(DateTime, nullable=True)
    last_update = Column(DateTime, nullable=True)
    last_flood_warn = Column(DateTime, nullable=True)  # Последнее предупреждение о flood wait
    
    # Статистика сессии (накапливается, но не сохраняется в инвентарь до сбора)
    session_hits = Column(Integer, default=0)
    session_ores = Column(BigInteger, default=0)  # Выкопано руды (power × hits)
    session_plasma = Column(Integer, default=0)
    session_cases = Column(Integer, default=0)
    
    # Инвентарь (JSON)
    inventory = Column(JSON, default=lambda: json.dumps({"ores": {}, "cases": {}, "items": {}}))
    
    # Боссы
    bosses_defeated = Column(JSON, default=lambda: json.dumps([]))
    
    # Параметры копания (для команды "шахта")
    case_chance = Column(Float, default=3.0)  # Шанс найти кейс (%)
    mining_duration = Column(Integer, default=300)  # Время копания (сек)
    
    # Бонусы за подписку на канал
    mining_bonus = Column(Float, default=1.0)  # Множитель добычи (1.0 = без бонуса, 1.5 = с бонусом)
    channel_subscribed = Column(Boolean, default=False)  # Подписан ли на @evo_ban_news
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MiningSession(Base):
    """Таблица активных сессий добычи"""
    __tablename__ = "mining_sessions"

    user_id = Column(BigInteger, primary_key=True)
    mine_id = Column(Integer, default=0)  # ID шахты
    mine_name = Column(String, nullable=True)  # Название шахты (напр. "Земля I")
    ore_name = Column(String, nullable=True)  # Название руды (напр. "земля")
    power = Column(Float, default=1.0)  # Мощность кирки
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    hits = Column(Integer, default=0)  # Количество ударов
    ores_dug = Column(BigInteger, default=0)  # Выкопано руды (power × hits)
    plasma_dug = Column(Integer, default=0)
    cases_found = Column(Integer, default=0)
    cases_list = Column(String, nullable=True)  # JSON список найденных кейсов
    is_active = Column(Boolean, default=False)
    last_update = Column(DateTime, default=datetime.utcnow)

    # Для авто-уведомления
    chat_id = Column(BigInteger, nullable=True)  # ID чата для отправки уведомления
    notification_sent = Column(Boolean, default=False)  # Флаг: уведомление отправлено


class UserSettings(Base):
    """Таблица настроек пользователя"""
    __tablename__ = "user_settings"

    user_id = Column(BigInteger, ForeignKey("users.id"), primary_key=True)
    notifications_enabled = Column(Boolean, default=True)  # Уведомления о завершении копания
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Inventory(Base):
    """Таблица инвентаря"""
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    item_type = Column(String, nullable=False)  # "ore", "case", "item"
    item_name = Column(String, nullable=False)  # Название предмета
    quantity = Column(BigInteger, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Transaction(Base):
    """Таблица транзакций"""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_user = Column(BigInteger, nullable=True)
    to_user = Column(BigInteger)
    amount = Column(BigInteger)
    timestamp = Column(DateTime, default=datetime.utcnow)
    type = Column(String)  # "transfer", "sale", "upgrade"


async def init_db(database_url: str):
    """Инициализация базы данных"""
    engine = create_async_engine(database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    """Получить пользователя"""
    return await session.get(User, user_id)


async def create_user(session: AsyncSession, user_id: int, username: str = None, first_name: str = None) -> User:
    """Создать нового пользователя"""
    user = User(
        id=user_id,
        username=username,
        first_name=first_name,
        inventory=json.dumps({"ores": {}, "cases": {}, "items": {}})
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_or_create_user(session: AsyncSession, user_id: int, username: str = None, first_name: str = None) -> User:
    """Получить или создать пользователя"""
    user = await get_user(session, user_id)
    if not user:
        user = await create_user(session, user_id, username, first_name)
    return user


async def get_or_create_user_settings(session: AsyncSession, user_id: int) -> UserSettings:
    """Получить или создать настройки пользователя"""
    from sqlalchemy import select
    result = await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = UserSettings(user_id=user_id, notifications_enabled=True)
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    
    return settings


async def toggle_notifications(session: AsyncSession, user_id: int) -> bool:
    """Переключить уведомления и вернуть новое состояние"""
    settings = await get_or_create_user_settings(session, user_id)
    settings.notifications_enabled = not settings.notifications_enabled
    settings.updated_at = datetime.utcnow()
    await session.commit()
    return settings.notifications_enabled


def parse_inventory(inventory_json: str) -> dict:
    """Парсинг инвентаря"""
    if isinstance(inventory_json, dict):
        return inventory_json
    if inventory_json is None:
        return {"ores": {}, "cases": {}, "items": {}}
    return json.loads(inventory_json)


def serialize_inventory(inventory: dict) -> str:
    """Сериализация инвентаря"""
    return json.dumps(inventory)
