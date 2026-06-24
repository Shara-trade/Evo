"""Проверка подписки на Telegram-канал @evo_ban_news"""
import logging
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

logger = logging.getLogger(__name__)

CHANNEL_USERNAME = "evo_ban_news"
CHANNEL_ID = -1002314288669  # ID канала @evo_ban_news (заменить на реальный при необходимости)

# Статусы, означающие подписку
SUBSCRIBED_STATUSES = {"member", "administrator", "creator"}


async def check_channel_subscription(bot: Bot, user_id: int, channel_username: str = CHANNEL_USERNAME) -> bool:
    """
    Проверить подписку пользователя на канал через getChatMember.
    
    Returns:
        True если подписан, False если нет.
    """
    try:
        # Пробуем получить информацию о членстве в канале
        chat_id = channel_username  # Можно использовать username
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        
        is_subscribed = member.status in SUBSCRIBED_STATUSES
        
        if is_subscribed:
            logger.info(f"✅ Пользователь {user_id} подписан на канал {channel_username}")
        else:
            logger.info(f"⚠️ Пользователь {user_id} НЕ подписан на канал {channel_username} (статус: {member.status})")
        
        return is_subscribed
        
    except TelegramForbiddenError:
        logger.error(f"❌ Бот не имеет доступа к каналу {channel_username}. Убедитесь, что бот добавлен как администратор.")
        return False
    except TelegramBadRequest as e:
        logger.error(f"❌ Ошибка при проверке подписки (TelegramBadRequest): {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке подписки пользователя {user_id}: {e}")
        return False


async def get_channel_invite_link(bot: Bot, channel_username: str = CHANNEL_USERNAME) -> str | None:
    """Получить ссылку-приглашение на канал."""
    try:
        link = await bot.get_chat_invite_link(chat_id=channel_username)
        return link.invite_link
    except Exception as e:
        logger.error(f"❌ Ошибка получения ссылки на канал: {e}")
        return None
