"""Миграция: добавление поля clan в таблицу users"""
import asyncio
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL


async def migrate():
    """Добавить поле clan в таблицу users"""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        async with engine.begin() as conn:
            # Проверяем, существует ли колонка clan
            result = await conn.execute(text("""
                SELECT name FROM pragma_table_info('users') WHERE name='clan'
            """))
            rows = result.fetchall()
            
            if rows:
                print("✅ Поле 'clan' уже существует")
                return
            
            # Добавляем поле clan
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN clan TEXT NULL
            """))
            print("✅ Поле 'clan' успешно добавлено")
            
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
