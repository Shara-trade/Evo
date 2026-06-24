"""Middleware для работы с сессией БД"""
from typing import Callable, Dict, Any
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import async_sessionmaker


class DatabaseMiddleware(BaseMiddleware):
    """Middleware для автоматического предоставления сессии БД"""
    
    def __init__(self, async_session: async_sessionmaker):
        self.async_session = async_session
    
    async def __call__(
        self,
        handler: Callable,
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        async with self.async_session() as session:
            data["session"] = session
            return await handler(event, data)
