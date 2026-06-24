"""Миграция: добавление полей mining_bonus и channel_subscribed в таблицу users"""
import asyncio
import asyncpg


async def migrate(pool: asyncpg.Pool):
    """Добавить колонки mining_bonus и channel_subscribed в таблицу users"""
    
    # Проверяем, существуют ли уже колонки
    async with pool.acquire() as conn:
        # Добавляем mining_bonus
        try:
            await conn.execute("""
                ALTER TABLE users 
                ADD COLUMN mining_bonus FLOAT DEFAULT 1.0
            """)
            print("✅ Колонка mining_bonus добавлена")
        except asyncpg.DuplicateColumnError:
            print("⚠️ Колонка mining_bonus уже существует")
        
        # Добавляем channel_subscribed
        try:
            await conn.execute("""
                ALTER TABLE users 
                ADD COLUMN channel_subscribed BOOLEAN DEFAULT FALSE
            """)
            print("✅ Колонка channel_subscribed добавлена")
        except asyncpg.DuplicateColumnError:
            print("⚠️ Колонка channel_subscribed уже существует")


async def main():
    """Запуск миграции"""
    import os
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    # Получаем URL базы данных
    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///mining_bot.db")
    
    # Для SQLite используем другой подход
    if "sqlite" in database_url:
        import aiosqlite
        import json
        
        # Парсим SQLite URL
        db_path = database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        
        async with aiosqlite.connect(db_path) as db:
            # Проверяем и добавляем колонки
            cursor = await db.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in await cursor.fetchall()]
            
            if "mining_bonus" not in columns:
                await db.execute("ALTER TABLE users ADD COLUMN mining_bonus FLOAT DEFAULT 1.0")
                print("✅ Колонка mining_bonus добавлена (SQLite)")
            else:
                print("⚠️ Колонка mining_bonus уже существует (SQLite)")
            
            if "channel_subscribed" not in columns:
                await db.execute("ALTER TABLE users ADD COLUMN channel_subscribed BOOLEAN DEFAULT 0")
                print("✅ Колонка channel_subscribed добавлена (SQLite)")
            else:
                print("⚠️ Колонка channel_subscribed уже существует (SQLite)")
            
            await db.commit()
    else:
        # Для PostgreSQL используем asyncpg
        from urllib.parse import urlparse
        
        parsed = urlparse(database_url.replace("postgresql+", ""))
        pool = await asyncpg.create_pool(
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            database=parsed.path.lstrip('/'),
            port=parsed.port or 5432
        )
        
        try:
            await migrate(pool)
        finally:
            await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
