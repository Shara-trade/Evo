"""Клавиатуры для бота"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
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
        # Копание активно - большая кнопка 🚫 Остановить, затем нижний ряд
        builder.button(text="🚫 Остановить", callback_data="stop_mining")
        builder.row(
            InlineKeyboardButton(text="Закрыть", callback_data="close_menu"),
            InlineKeyboardButton(text="🔄", callback_data="update_mining")
        )
        # Кнопка обновления всегда активна
        
    elif can_collect:
        # Копание завершено, можно собрать
        builder.button(text="🧱 Собрать", callback_data="collect_resources")
        builder.button(text="Закрыть", callback_data="close_menu")
        builder.adjust(1)
    
    return builder.as_markup()


def get_mining_finished_keyboard(notifications_enabled: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура для уведомления о завершении по таймеру
    Кнопки:
    - 🧱 Собрать (большая центральная)
    - Закрыть | 🔔 (в ряд)
    """
    builder = InlineKeyboardBuilder()
    
    # Большая центральная кнопка
    builder.button(text="🧱 Собрать", callback_data="collect_from_notification")
    
    # Нижний ряд: Закрыть и переключатель уведомлений
    toggle_text = "🔔" if notifications_enabled else "🔕"
    builder.row(
        InlineKeyboardButton(text="Закрыть", callback_data="close_menu"),
        InlineKeyboardButton(text=toggle_text, callback_data="toggle_notifications")
    )
    
    return builder.as_markup()


def get_collect_completed_keyboard(mine_name: str, hits: int, ores: int, plasma: int) -> InlineKeyboardMarkup:
    """Клавиатура для сообщения о сборе ресурсов
    Кнопки:
    - ⛏ Добывать еще (большая центральная)
    - Закрыть | 🎒 Рюкзак (в ряд)
    """
    builder = InlineKeyboardBuilder()
    
    # Большая центральная кнопка
    builder.button(text="⛏ Добывать еще", callback_data="start_mining")
    
    # Нижний ряд
    builder.row(
        InlineKeyboardButton(text="Закрыть", callback_data="close_menu"),
        InlineKeyboardButton(text="🎒 Рюкзак", callback_data="inventory")
    )
    
    return builder.as_markup()


def get_inventory_keyboard(ore_count: int = 0) -> InlineKeyboardMarkup:
    """Клавиатура инвентаря с вкладками
    Кнопки:
    - 💸 Продать (большая центральная)
    - 🧱 | 🎨 | 🧪 (в ряд - вкладки)
    - Закрыть (большая центральная)
    """
    builder = InlineKeyboardBuilder()
    
    # Большая кнопка продажи
    builder.button(text="💸 Продать", callback_data="sell_all_ores")
    
    # Вкладки
    builder.row(
        InlineKeyboardButton(text="🧱", callback_data="inv_tab_ore"),
        InlineKeyboardButton(text="🎨", callback_data="inv_tab_materials"),
        InlineKeyboardButton(text="🧪", callback_data="inv_tab_consumables")
    )
    
    # Кнопка закрытия
    builder.button(text="Закрыть", callback_data="close_menu")
    
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
    builder.button(text="👤 Профиль", callback_data="profile")
    
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


def get_profile_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура профиля"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="🔙 Назад", callback_data="close_profile")
    builder.adjust(1)
    
    return builder.as_markup()


def get_start_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню (/start)"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="помощь"), KeyboardButton(text="профиль")],
            [KeyboardButton(text="донат"), KeyboardButton(text="прочее")],
            [KeyboardButton(text="старт")],
        ],
        resize_keyboard=True,
    )
    return keyboard


def get_sos_keyboard() -> InlineKeyboardMarkup:
    """Меню SOS (помощь)"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📚 Как играть?", callback_data="help_howto"),
                InlineKeyboardButton(text="✏️ Команды", callback_data="help_commands"),
            ],
            [
                InlineKeyboardButton(text="📄 Правила проекта", callback_data="help_rules"),
                InlineKeyboardButton(text="❓ Частые вопросы", callback_data="help_faq"),
            ],
            [InlineKeyboardButton(text="🏰 Кланы", callback_data="help_clans")],
            [InlineKeyboardButton(text="🛡️ Администрирование чата", callback_data="help_admin")],
            [InlineKeyboardButton(text="💰 Донат", callback_data="help_donate")],
        ]
    )
    return keyboard


def get_donate_keyboard() -> InlineKeyboardMarkup:
    """Меню Донатик"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💥 Бандл 💥", callback_data="donate_bundle")],
            [
                InlineKeyboardButton(text="⚜️", callback_data="donate_1"),
                InlineKeyboardButton(text="🎇", callback_data="donate_2"),
                InlineKeyboardButton(text="🪄", callback_data="donate_3"),
                InlineKeyboardButton(text="💎", callback_data="donate_4"),
            ],
            [InlineKeyboardButton(text="💳 Пополнить 💳", callback_data="donate_topup")],
            [InlineKeyboardButton(text="Закрыть", callback_data="donate_close")],
        ]
    )
    return keyboard


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой назад"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]]
    )
    return keyboard


def get_subscription_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой подписки на канал"""
    builder = InlineKeyboardBuilder()
    
    # Кнопка подписки
    builder.button(
        text="📢 Подписаться на канал",
        url="https://t.me/evo_ban_news"
    )
    
    # Кнопка проверки (после подписки)
    builder.button(
        text="✅ Я подписался — проверить",
        callback_data="check_subscription"
    )
    
    builder.button(
        text="Закрыть",
        callback_data="close_menu"
    )
    builder.adjust(1)
    
    return builder.as_markup()
