"""Миграция: добавление таблицы user_settings"""
import asyncio
import sqlite3
from pathlib import Path

DB_PATH = Path("mining_bot.db")


async def migrate():
    """Добавить таблицу user_settings"""
    if not DB_PATH.exists():
        print(f"DB {DB_PATH} not found. Run the bot first.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Проверяем, существует ли таблица
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_settings'")
        if cursor.fetchone():
            print("Table user_settings already exists")
        else:
            # Создаём таблицу
            cursor.execute("""
                CREATE TABLE user_settings (
                    user_id INTEGER PRIMARY KEY,
                    notifications_enabled BOOLEAN DEFAULT 1,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            print("Created table: user_settings")
        
        conn.commit()
        print("Migration completed!")
        
    except Exception as e:
        print(f"Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
