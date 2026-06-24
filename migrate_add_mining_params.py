"""Миграция: добавить поля case_chance и mining_duration в таблицу users"""
import sqlite3
import os


def migrate(db_path: str = "EvoBan_bot.db"):
    """Добавить колонки case_chance и mining_duration в таблицу users"""
    
    if not os.path.exists(db_path):
        print("WARNING: Database not found, skipping migration")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Проверяем, существуют ли уже колонки
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "case_chance" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN case_chance REAL DEFAULT 3.0")
        print("OK: Added column case_chance")
    else:
        print("INFO: Column case_chance already exists")
    
    if "mining_duration" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN mining_duration INTEGER DEFAULT 300")
        print("OK: Added column mining_duration")
    else:
        print("INFO: Column mining_duration already exists")
    
    conn.commit()
    conn.close()
    print("OK: Migration completed")


if __name__ == "__main__":
    migrate()
