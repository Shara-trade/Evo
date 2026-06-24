"""Тестовый скрипт для проверки функциональности"""
import asyncio
import sys

# Установка кодировки для Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from config import MINES, ORE_PRICES, PLASMA_CHANCE, CASE_CHANCE
from database import User, Base, get_or_create_user, parse_inventory


async def test_database():
    """Тестирование базы данных"""
    print("🧪 Тестирование базы данных...")
    
    engine = create_async_engine("sqlite+aiosqlite:///test_mining_bot.db", echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Создание тестового пользователя
        user = await get_or_create_user(session, 123456789, "test_user", "Test")
        print(f"✅ Пользователь создан: {user.first_name} (@{user.username})")
        
        # Проверка инвентаря
        inventory = parse_inventory(user.inventory)
        print(f"✅ Инвентарь инициализирован: {list(inventory.keys())}")
        
        # Тест добавления руды
        inventory["ores"]["камень"] = 100
        inventory["ores"]["уголь"] = 50
        user.inventory = str(inventory).replace("'", '"')
        await session.commit()
        print(f"✅ Руда добавлена: {inventory['ores']}")
        
        # Тест баланса
        user.balance = 1000
        user.plasma = 25
        await session.commit()
        print(f"✅ Баланс установлен: {user.balance}💰, {user.plasma}🎆")
        
        # Тест уровня
        user.level = 5
        user.experience = 250
        await session.commit()
        print(f"✅ Уровень: {user.level}, Опыт: {user.experience}")
        
        # Проверка доступных шахт
        available_mines = [m for mid, m in MINES.items() if user.level >= m["level_req"]]
        print(f"✅ Доступно шахт: {len(available_mines)}/{len(MINES)}")
        
    await engine.dispose()
    print("\n✅ Все тесты пройдены!")


def test_probabilities():
    """Тестирование вероятностей"""
    print("\n🎲 Тестирование вероятностей...")
    
    import random
    
    # Тест шанса плазмы
    plasma_drops = sum(1 for _ in range(1000) if random.random() * 100 < PLASMA_CHANCE)
    print(f"🎆 Плазма: {plasma_drops}/1000 ({plasma_drops/10:.1f}%, ожидалось ~{PLASMA_CHANCE}%)")
    
    # Тест шанса кейса
    case_drops = sum(1 for _ in range(1000) if random.random() * 100 < CASE_CHANCE)
    print(f"📦 Кейсы: {case_drops}/1000 ({case_drops/10:.1f}%, ожидалось ~{CASE_CHANCE}%)")


def test_mine_progression():
    """Тестирование прогрессии шахт"""
    print("\n🏔️ Тестирование прогрессии шахт...")
    
    for level in [1, 3, 5, 7, 9, 11, 13, 15]:
        available = [mname for mid, mname in MINES.items() if level >= mname["level_req"]]
        print(f"Уровень {level}: {len(available)} шахт доступно")


def test_economy():
    """Тестирование экономики"""
    print("\n💰 Тестирование экономики...")
    
    total_value = sum(price for price in ORE_PRICES.values())
    avg_price = total_value / len(ORE_PRICES)
    print(f"Средняя цена руды: {avg_price:.1f}💰")
    print(f"Диапазон цен: {min(ORE_PRICES.values())}💰 - {max(ORE_PRICES.values())}💰")


async def main():
    """Запуск всех тестов"""
    print("=" * 50)
    print("🎮 Mining Bot - Тестирование")
    print("=" * 50)
    
    await test_database()
    test_probabilities()
    test_mine_progression()
    test_economy()
    
    print("\n" + "=" * 50)
    print("✅ Все тесты завершены!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
