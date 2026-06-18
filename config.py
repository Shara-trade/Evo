"""Конфигурация бота"""
import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# База данных
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///mining_bot.db")

# Настройки добычи
BASE_MINING_TIME = 300  # 5 минут в секундах
FLOOD_WAIT_WARN = 120  # 2 минуты - предупреждение о flood wait

# Шансы
PLASMA_CHANCE = 5.0  # 5% шанс выпадения плазмы (можно улучшить до 75%)
CASE_CHANCE = 3.0  # 3% шанс выпадения кейса

# Типы кейсов
CASE_TYPES = ["коробка", "конверт", "сумка", "ящик", "портфель"]

# Улучшения
UPGRADES = {
    "кирка": {"base_power": 1, "cost_multiplier": 1.5},
    "бустер": {"base_power": 1, "cost_multiplier": 2.0},
}

# Лимиты переводов
BASE_TRANSFER_LIMIT = 1000
LIMIT_PER_LEVEL = 100

# Боссы
BOSS_LEVELS = [15, 30, 45, 60, 75, 90, 105, 120, 135, 150]

# Цены на руду (по типам шахт)
ORE_PRICES = {
    "земля": 1,
    "пещера": 8,
    "гора": 30,
    "кристалл": 150,
}
