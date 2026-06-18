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

# Типы руды и шахты
MINES = {
    0: {"name": "Земля I", "level_req": 1, "ores": ["камень", "уголь"]},
    1: {"name": "Земля II", "level_req": 3, "ores": ["камень", "уголь", "железо"]},
    2: {"name": "Пещера I", "level_req": 5, "ores": ["уголь", "железо", "медь"]},
    3: {"name": "Пещера II", "level_req": 7, "ores": ["железо", "медь", "серебро"]},
    4: {"name": "Гора I", "level_req": 9, "ores": ["медь", "серебро", "золото"]},
    5: {"name": "Гора II", "level_req": 11, "ores": ["серебро", "золото", "изумруд"]},
    6: {"name": "Кристалл I", "level_req": 13, "ores": ["золото", "изумруд", "алмаз"]},
    7: {"name": "Кристалл II", "level_req": 15, "ores": ["изумруд", "алмаз", "платина"]},
}

# Цены на руду
ORE_PRICES = {
    "камень": 1,
    "уголь": 3,
    "железо": 8,
    "медь": 15,
    "серебро": 30,
    "золото": 75,
    "изумруд": 150,
    "алмаз": 300,
    "платина": 600,
}

# Шансы выпадения (в процентах)
ORE_CHANCES = {
    "камень": 40,
    "уголь": 25,
    "железо": 15,
    "медь": 10,
    "серебро": 6,
    "золото": 3,
    "изумруд": 1,
    "алмаз": 0.5,
    "платина": 0.2,
}

PLASMA_CHANCE = 5  # 5% шанс выпадения плазмы (можно улучшить до 75%)
CASE_CHANCE = 3  # 3% шанс выпадения кейса

# Типы кейсов
CASE_TYPES = ["коробка", "конверт", "сумка", "ящик", "портфель"]

# Кейсы
CASES = {
    "деревянный": {"chance": 50, "min_plasma": 1, "max_plasma": 5},
    "железный": {"chance": 30, "min_plasma": 5, "max_plasma": 15},
    "золотой": {"chance": 15, "min_plasma": 15, "max_plasma": 50},
    "легендарный": {"chance": 5, "min_plasma": 50, "max_plasma": 200},
}

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
