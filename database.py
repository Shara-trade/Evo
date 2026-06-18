"""Модуль работы с базой данных"""
from sqlalchemy import Column, Integer, String, BigInteger, Float, Boolean, DateTime, JSON
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import json

Base = declarative_base()


class User(Base):
    """Таблица пользователей"""
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    
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
    
    # Состояние добычи
    is_mining = Column(Boolean, default=False)
    current_mine = Column(Integer, default=0)
    mining_start = Column(DateTime, nullable=True)
    mining_end = Column(DateTime, nullable=True)
    last_update = Column(DateTime, nullable=True)
    
    # Статистика сессии
    session_hits = Column(Integer, default=0)
    session_ores = Column(Integer, default=0)
    session_plasma = Column(Integer, default=0)
    
    # Инвентарь (JSON)
    inventory = Column(JSON, default=lambda: json.dumps({"ores": {}, "cases": {}, "items": {}}))
    
    # Боссы
    bosses_defeated = Column(JSON, default=lambda: json.dumps([]))
    
    created_at = Column(DateTime, default=datetime.utcnow)
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
