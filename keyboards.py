"""Клавиатуры для бота"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_mining_menu_keyboard(is_mining: bool = False, mining_active: bool = False, can_collect: bool = False, show_flood_warn: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура меню добычи"""
    builder = InlineKeyboardBuilder()
    
    if not is_mining:
        # Копание не запущено
        builder.button(text="🔨 Добывать", callback_data="start_mining")
        builder.button(text="Закрыть", callback_data="close_menu")
        builder.adjust(1)  # Кнопки друг под другом
        
    elif mining_active:
        # Копание активно - кнопка 🔄 ВСЕГДА доступна
        builder.button(text="🚫 Остановить", callback_data="stop_mining")
        builder.row(
            InlineKeyboardButton(text="Закрыть", callback_data="close_menu"),
            InlineKeyboardButton(text="🔄", callback_data="update_mining")
        )
        # Кнопка обновления всегда активна, предупреждение в тексте сообщения
        
    elif can_collect:
        # Копание завершено, можно собрать
        builder.button(text="🧱 Собрать", callback_data="collect_resources")
        builder.button(text="Закрыть", callback_data="close_menu")
        builder.adjust(1)
    
    return builder.as_markup()


def get_mines_keyboard(user_level: int, current_mine: int = 0) -> InlineKeyboardMarkup:
    """Клавиатура выбора шахты"""
    from config import MINES
    
    builder = InlineKeyboardBuilder()
    
    for mine_id, mine_data in MINES.items():
        if user_level >= mine_data["level_req"]:
            status = "✅" if mine_id == current_mine else ""
            builder.button(
                text=f"{status} {mine_data['name']} (ур. {mine_data['level_req']})",
                callback_data=f"select_mine_{mine_id}"
            )
    
    builder.button(text="🔙 Назад", callback_data="back_to_mining")
    builder.adjust(1)
    
    return builder.as_markup()


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="⛏️ Добывать", callback_data="mining_menu")
    builder.button(text="🎒 Инвентарь", callback_data="inventory")
    builder.button(text="💵 Баланс", callback_data="balance")
    builder.button(text="📈 Уровень", callback_data="level_info")
    builder.button(text="🔄 Перевод", callback_data="transfer_menu")
    builder.button(text="🏪 Магазин", callback_data="shop")
    builder.button(text="👥 Профиль", callback_data="profile")
    
    builder.adjust(1)
    
    return builder.as_markup()


def get_inventory_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура инвентаря"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="💵 Продать всю руду", callback_data="sell_all_ores")
    builder.button(text="🔙 Назад", callback_data="main_menu")
    builder.adjust(1)
    
    return builder.as_markup()


def get_transfer_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура перевода"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="🔙 Назад", callback_data="main_menu")
    builder.adjust(1)
    
    return builder.as_markup()


def get_shop_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура магазина"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="⚒️ Улучшить кирку", callback_data="upgrade_pickaxe")
    builder.button(text="🚀 Купить бустер", callback_data="buy_booster")
    builder.button(text="🔙 Назад", callback_data="main_menu")
    builder.adjust(1)
    
    return builder.as_markup()


def get_confirmation_keyboard(confirm_data: str, cancel_data: str = "main_menu") -> InlineKeyboardMarkup:
    """Клавиатура подтверждения"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="✅ Подтвердить", callback_data=confirm_data)
    builder.button(text="❌ Отмена", callback_data=cancel_data)
    builder.adjust(2)
    
    return builder.as_markup()


def get_boss_keyboard(boss_id: int) -> InlineKeyboardMarkup:
    """Клавиатура боя с боссом"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="⚔️ Атаковать", callback_data=f"attack_boss_{boss_id}")
    builder.button(text="🏃 Сбежать", callback_data="flee_boss")
    builder.adjust(2)
    
    return builder.as_markup()
