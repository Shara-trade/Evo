"""Миграция: добавление колонок chat_id и notification_sent в mining_sessions"""
import asyncio
import sqlite3
from pathlib import Path

DB_PATH = Path("mining_bot.db")


async def migrate():
    """Добавить новые колонки в таблицу mining_sessions"""
    if not DB_PATH.exists():
        print(f"DB {DB_PATH} not found. Run the bot first.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check existing columns
        cursor.execute("PRAGMA table_info(mining_sessions)")
        columns = {col[1] for col in cursor.fetchall()}
        
        # Add chat_id if not exists
        if "chat_id" not in columns:
            cursor.execute("ALTER TABLE mining_sessions ADD COLUMN chat_id INTEGER")
            print("Added column: chat_id")
        else:
            print("Column chat_id already exists")
        
        # Add notification_sent if not exists
        if "notification_sent" not in columns:
            cursor.execute("ALTER TABLE mining_sessions ADD COLUMN notification_sent BOOLEAN DEFAULT 0")
            print("Added column: notification_sent")
        else:
            print("Column notification_sent already exists")
        
        conn.commit()
        print("Migration completed!")
        
    except Exception as e:
        print(f"Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
