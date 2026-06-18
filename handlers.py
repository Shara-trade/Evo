"""Обработчики команд и callback-ов"""
import random
import asyncio
from datetime import datetime, timedelta
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandStart
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    MINES, ORE_PRICES, ORE_CHANCES, PLASMA_CHANCE, CASE_CHANCE,
    BASE_MINING_TIME, FLOOD_WAIT, CASES, UPGRADES,
    BASE_TRANSFER_LIMIT, LIMIT_PER_LEVEL, BOSS_LEVELS
)
from database import get_or_create_user, parse_inventory, serialize_inventory
from keyboards import (
    get_mining_menu_keyboard, get_mines_keyboard, get_main_menu_keyboard,
    get_inventory_keyboard, get_transfer_keyboard, get_shop_keyboard,
    get_confirmation_keyboard
)
from states import MiningState, TransferState

router = Router()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_available_mines(level: int) -> dict:
    """Получить доступные шахты для уровня"""
    return {mid: mdata for mid, mdata in MINES.items() if level >= mdata["level_req"]}


def calculate_power(pickaxe: float, booster: float) -> float:
    """Расчёт общей мощности"""
    return pickaxe * booster


def get_ore_drop(mine_id: int) -> str | None:
    """Определить выпавшую руду"""
    if mine_id not in MINES:
        return None
    
    available_ores = MINES[mine_id]["ores"]
    weights = [ORE_CHANCES.get(ore, 10) for ore in available_ores]
    
    total = sum(weights)
    normalized_weights = [w / total for w in weights]
    
    return random.choices(available_ores, weights=normalized_weights)[0]


def check_plasma_drop() -> bool:
    """Проверка выпадения плазмы"""
    return random.random() * 100 < PLASMA_CHANCE


def check_case_drop() -> str | None:
    """Проверка выпадения кейса"""
    if random.random() * 100 >= CASE_CHANCE:
        return None
    
    case_types = list(CASES.keys())
    weights = [CASES[c]["chance"] for c in case_types]
    total = sum(weights)
    normalized_weights = [w / total for w in weights]
    
    return random.choices(case_types, weights=normalized_weights)[0]


def format_time(seconds: int) -> str:
    """Форматирование времени"""
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins}м. {secs}с."


def check_level_up(current_exp: int, level: int) -> tuple[int, int, bool]:
    """Проверка повышения уровня"""
    exp_needed = level * 100
    if current_exp >= exp_needed:
        return current_exp - exp_needed, level + 1, True
    return current_exp, level, False


def check_boss_spawn(level: int) -> bool:
    """Проверка спавна босса"""
    return level in BOSS_LEVELS


# ==================== ОСНОВНЫЕ КОМАНДЫ ====================

@router.message(CommandStart())
async def cmd_start(message: types.Message, session: AsyncSession):
    """Команда /start"""
    user = await get_or_create_user(
        session, 
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Добро пожаловать в Mining Bot! 🎮\n\n"
        "📜 <b>Как играть:</b>\n"
        "• ⛏️ Добывай руду в AFK-режиме\n"
        "• 💰 Продавай руду и зарабатывай деньги\n"
        "• 🎆 Собирай плазму для улучшений\n"
        "• 📦 Находи кейсы с ценными ресурсами\n"
        "• 🆙 Повышай уровень и открывай новые шахты\n"
        "• 👹 Сражайся с боссами каждые 15 уровней!\n\n"
        "Используй кнопки ниже для навигации."
    )
    
    await message.answer(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")


@router.message(Command("menu"))
async def cmd_menu(message: types.Message, session: AsyncSession):
    """Команда /menu"""
    await get_or_create_user(session, message.from_user.id)
    await message.answer("📋 Главное меню:", reply_markup=get_main_menu_keyboard())


@router.message(Command("bal") | F.text.lower().regex(r"^б$"))
async def cmd_balance(message: types.Message, session: AsyncSession):
    """Команда /bal или Б"""
    user = await get_or_create_user(session, message.from_user.id)
    
    text = (
        f"💰 <b>Ваш баланс</b>\n\n"
        f"💵 Деньги: <b>{user.balance:,}</b>\n"
        f"🎆 Плазма: <b>{user.plasma:,}</b>\n"
        f"📊 Уровень: <b>{user.level}</b>"
    )
    
    await message.answer(text, parse_mode="HTML")


@router.message(Command("inv"))
async def cmd_inventory(message: types.Message, session: AsyncSession):
    """Команда /inv"""
    user = await get_or_create_user(session, message.from_user.id)
    inventory = parse_inventory(user.inventory)
    
    text = "🎒 <b>Инвентарь</b>\n\n"
    
    # Руда
    ores = inventory.get("ores", {})
    if ores:
        text += "⛏️ <b>Руда:</b>\n"
        for ore_name, count in ores.items():
            if count > 0:
                price = ORE_PRICES.get(ore_name, 0)
                text += f"  • {ore_name.capitalize()}: {count:,} ({price}💰/шт)\n"
    else:
        text += "⛏️ Руда: пуста\n"
    
    # Кейсы
    cases = inventory.get("cases", {})
    if cases:
        text += "\n📦 <b>Кейсы:</b>\n"
        for case_name, count in cases.items():
            if count > 0:
                text += f"  • {case_name.capitalize()}: {count}\n"
    else:
        text += "\n📦 Кейсы: нет\n"
    
    # Предметы
    items = inventory.get("items", {})
    if items:
        text += "\n🎁 <b>Предметы:</b>\n"
        for item_name, count in items.items():
            if count > 0:
                text += f"  • {item_name}: {count}\n"
    
    await message.answer(text, reply_markup=get_inventory_keyboard(), parse_mode="HTML")


@router.message(Command("lvl") | F.text == "Меню → Уровень")
async def cmd_level(message: types.Message, session: AsyncSession):
    """Команда /lvl"""
    user = await get_or_create_user(session, message.from_user.id)
    
    exp_needed = user.level * 100
    exp_progress = (user.experience / exp_needed) * 100
    
    text = (
        f"📈 <b>Ваш уровень</b>\n\n"
        f"🔢 Уровень: <b>{user.level}</b>\n"
        f"📊 Опыт: <b>{user.experience:,}/{exp_needed:,}</b> ({exp_progress:.1f}%)\n\n"
        f"⚒️ Мощность кирки: ×{user.pickaxe_power:.2f}\n"
        f"🚀 Мощность бустера: ×{user.booster_power:.2f}\n"
        f"💪 <b>Общая мощность: ×{calculate_power(user.pickaxe_power, user.booster_power):.2f}</b>\n\n"
    )
    
    # Доступные шахты
    available = get_available_mines(user.level)
    text += f"🏔️ <b>Доступно шахт:</b> {len(available)}/{len(MINES)}\n"
    
    # Боссы
    bosses_defeated = len(parse_inventory(user.bosses_defeated) if isinstance(user.bosses_defeated, str) else user.bosses_defeated)
    text += f"👹 <b>Боссов побеждено:</b> {bosses_defeated}\n"
    
    # Лимит
    text += f"\n💸 <b>Лимит получения:</b> {user.transfer_limit:,}💰"
    
    await message.answer(text, parse_mode="HTML")


@router.message(Command("limit") | F.text == "Лимит")
async def cmd_limit(message: types.Message, session: AsyncSession):
    """Команда Лимит"""
    user = await get_or_create_user(session, message.from_user.id)
    
    # Сброс лимита каждый день
    now = datetime.utcnow()
    if user.last_reset and now.date() > user.last_reset.date():
        user.received_today = 0
        user.last_reset = now
    
    text = (
        f"💸 <b>Лимит переводов</b>\n\n"
        f"📊 Макс. получение: <b>{user.transfer_limit:,}💰</b>\n"
        f"📥 Получено сегодня: <b>{user.received_today:,}/{user.transfer_limit:,}💰</b>\n"
        f"📈 Осталось: <b>{user.transfer_limit - user.received_today:,}💰</b>\n\n"
        f"<i>Лимит увеличивается с уровнем (+{LIMIT_PER_LEVEL} за уровень)</i>"
    )
    
    await message.answer(text, parse_mode="HTML")


# ==================== МЕНЮ ДОБЫЧИ ====================

@router.callback_query(F.data == "mining_menu")
async def cb_mining_menu(callback: types.CallbackQuery, session: AsyncSession):
    """Меню добычи"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    mine_name = MINES.get(user.current_mine, MINES[0])["name"]
    power = calculate_power(user.pickaxe_power, user.booster_power)
    max_time = BASE_MINING_TIME
    
    now = datetime.utcnow()
    
    if user.is_mining and user.mining_end:
        if now < user.mining_end:
            # Активное копание
            remaining = (user.mining_end - now).total_seconds()
            text = (
                f"⛏️ <b>Вы копаете</b>\n\n"
                f"{'.' * 30}\n"
                f"⛰️ Шахта: {mine_name}\n"
                f"🔥 Мощность: ×{power:.2f}\n"
                f"{'.' * 30}\n"
                f"⛏️ Удары киркой: {user.session_hits}\n"
                f"🧱 Руды добыто: {user.session_ores}\n"
                f"🎆 Плазмы добыто: {user.session_plasma}\n"
                f"{'.' * 30}\n"
                f"⏳ Осталось копать: {format_time(int(remaining))}"
            )
            await callback.message.edit_text(text, reply_markup=get_mining_menu_keyboard(is_mining=True, mining_active=True), parse_mode="HTML")
        else:
            # Копание завершено
            text = (
                f"⛏️ <b>Копание завершено!</b>\n\n"
                f"{'.' * 30}\n"
                f"⛰️ Шахта: {mine_name}\n"
                f"⏳ Время копания: {format_time(BASE_MINING_TIME)}\n"
                f"{'.' * 30}\n"
                f"⛏️ Удары киркой: {user.session_hits}\n"
                f"🧱 Руды добыто: {user.session_ores}\n"
                f"🎆 Плазмы добыто: {user.session_plasma}\n"
                f"{'.' * 30}\n"
                f"<i>Соберите ресурсы, чтобы отправиться в шахту.</i>"
            )
            await callback.message.edit_text(text, reply_markup=get_mining_menu_keyboard(is_mining=True, can_collect=True), parse_mode="HTML")
    else:
        # Копание не запущено
        text = (
            f"⛏️ <b>Копание</b>\n\n"
            f"{'.' * 30}\n"
            f"⛰️ Выбрана шахта: {mine_name}\n"
            f"🔥 Мощность: ×{power:.2f}\n"
            f"⏳ Время копания: {format_time(max_time)}\n"
            f"{'.' * 30}\n"
            f"<i>Отправься в шахту чтобы начать добычу руду!</i>"
        )
        await callback.message.edit_text(text, reply_markup=get_mining_menu_keyboard(), parse_mode="HTML")
    
    await callback.answer()


@router.callback_query(F.data == "start_mining")
async def cb_start_mining(callback: types.CallbackQuery, session: AsyncSession):
    """Начать добычу"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    if user.is_mining:
        await callback.answer("⚠️ Вы уже копаете!", show_alert=True)
        return
    
    now = datetime.utcnow()
    user.is_mining = True
    user.mining_start = now
    user.mining_end = now + timedelta(seconds=BASE_MINING_TIME)
    user.last_update = now
    user.session_hits = 0
    user.session_ores = 0
    user.session_plasma = 0
    
    await session.commit()
    
    await callback.message.edit_text(
        "⛏️ Вы начали добычу!\n\n"
        f"⏳ Время: {format_time(BASE_MINING_TIME)}",
        reply_markup=get_mining_menu_keyboard(is_mining=True, mining_active=True)
    )
    await callback.answer("Добыча началась! 🎉")


@router.callback_query(F.data == "update_mining")
async def cb_update_mining(callback: types.CallbackQuery, session: AsyncSession):
    """Обновить статус добычи"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    if not user.is_mining:
        await callback.answer("⚠️ Вы не копаете!", show_alert=True)
        return
    
    now = datetime.utcnow()
    
    # Проверка flood wait
    if user.last_update:
        elapsed = (now - user.last_update).total_seconds()
        if elapsed < FLOOD_WAIT:
            remaining_wait = int(FLOOD_WAIT - elapsed)
            await callback.answer(f"⏳ Подождите {remaining_wait}с. перед обновлением", show_alert=True)
            return
    
    # Проверка завершения
    if user.mining_end and now >= user.mining_end:
        user.is_mining = False
        await session.commit()
        await cb_mining_menu(callback, session)
        return
    
    # Обновление статистики (симуляция)
    elapsed_total = (now - user.mining_start).total_seconds()
    hits = int(elapsed_total * 0.5)  # 1 удар в 2 секунды
    
    user.session_hits = hits
    user.last_update = now
    
    await session.commit()
    
    await cb_mining_menu(callback, session)
    await callback.answer("Обновлено! 🔄")


@router.callback_query(F.data == "stop_mining")
async def cb_stop_mining(callback: types.CallbackQuery, session: AsyncSession):
    """Остановить добычу"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    if not user.is_mining:
        await callback.answer("⚠️ Вы не копаете!", show_alert=True)
        return
    
    user.is_mining = False
    user.mining_end = datetime.utcnow()
    
    await session.commit()
    
    await cb_mining_menu(callback, session)
    await callback.answer("Добыча остановлена ⏹️")


@router.callback_query(F.data == "collect_resources")
async def cb_collect_resources(callback: types.CallbackQuery, session: AsyncSession):
    """Собрать ресурсы"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    if not user.session_ores:
        await callback.answer("⚠️ Нечего собирать!", show_alert=True)
        return
    
    inventory = parse_inventory(user.inventory)
    
    # Добавляем руду
    ores_collected = user.session_ores
    ore_type = get_ore_drop(user.current_mine)
    if ore_type:
        inventory["ores"][ore_type] = inventory["ores"].get(ore_type, 0) + ores_collected
    
    # Добавляем плазму
    if user.session_plasma > 0:
        user.plasma += user.session_plasma
    
    # Добавляем кейсы
    cases_found = int(user.session_hits * CASE_CHANCE / 100)
    for _ in range(cases_found):
        case_type = check_case_drop()
        if case_type:
            inventory["cases"][case_type] = inventory["cases"].get(case_type, 0) + 1
    
    # Опыт
    exp_gained = ores_collected * 2
    user.experience += exp_gained
    
    # Проверка уровня
    new_exp, new_level, leveled_up = check_level_up(user.experience, user.level)
    user.experience = new_exp
    user.level = new_level
    
    if leveled_up:
        user.transfer_limit = BASE_TRANSFER_LIMIT + (new_level * LIMIT_PER_LEVEL)
    
    # Проверка босса
    if check_boss_spawn(new_level):
        await callback.answer(f"👹 БОСС ПОЯВИЛСЯ! Уровень {new_level}!", show_alert=True)
        # Здесь можно добавить механику босса
    
    # Сброс сессии
    user.session_hits = 0
    user.session_ores = 0
    user.session_plasma = 0
    user.mining_start = None
    user.mining_end = None
    user.inventory = serialize_inventory(inventory)
    
    await session.commit()
    
    await callback.message.edit_text(
        f"🧱 <b>Ресурсы собраны!</b>\n\n"
        f"⛏️ Добыто руды: {ores_collected}\n"
        f"🎆 Плазмы: {user.session_plasma}\n"
        f"📦 Кейсов: {cases_found}\n"
        f"⭐ Опыт: +{exp_gained}\n"
        f"{'🎉 Уровень повышен!' if leveled_up else ''}",
        reply_markup=get_mining_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer("Ресурсы собраны! 🎒")


@router.callback_query(F.data.startswith("select_mine_"))
async def cb_select_mine(callback: types.CallbackQuery, session: AsyncSession):
    """Выбор шахты"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    mine_id = int(callback.data.split("_")[-1])
    
    if mine_id not in MINES:
        await callback.answer("⚠️ Шахта не найдена!", show_alert=True)
        return
    
    if user.level < MINES[mine_id]["level_req"]:
        await callback.answer("⚠️ Недостаточный уровень!", show_alert=True)
        return
    
    user.current_mine = mine_id
    await session.commit()
    
    await callback.answer(f"Выбрана шахта: {MINES[mine_id]['name']} ✅")
    await cb_mining_menu(callback, session)


@router.callback_query(F.data == "back_to_mining")
async def cb_back_to_mining(callback: types.CallbackQuery, session: AsyncSession):
    """Назад к добыче"""
    await cb_mining_menu(callback, session)


# ==================== ИНВЕНТАРЬ И ПРОДАЖА ====================

@router.callback_query(F.data == "inventory")
async def cb_inventory(callback: types.CallbackQuery, session: AsyncSession):
    """Инвентарь"""
    user = await get_or_create_user(session, callback.from_user.id)
    inventory = parse_inventory(user.inventory)
    
    text = "🎒 <b>Инвентарь</b>\n\n"
    
    ores = inventory.get("ores", {})
    if ores:
        text += "⛏️ <b>Руда:</b>\n"
        for ore_name, count in ores.items():
            if count > 0:
                price = ORE_PRICES.get(ore_name, 0)
                text += f"  • {ore_name.capitalize()}: {count:,} ({price}💰/шт)\n"
    else:
        text += "⛏️ Руда: пуста\n"
    
    cases = inventory.get("cases", {})
    if cases:
        text += "\n📦 <b>Кейсы:</b>\n"
        for case_name, count in cases.items():
            if count > 0:
                text += f"  • {case_name.capitalize()}: {count}\n"
    
    await callback.message.edit_text(text, reply_markup=get_inventory_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "sell_all_ores")
async def cb_sell_all(callback: types.CallbackQuery, session: AsyncSession):
    """Продать всю руду"""
    user = await get_or_create_user(session, callback.from_user.id)
    inventory = parse_inventory(user.inventory)
    
    ores = inventory.get("ores", {})
    total_earned = 0
    total_sold = 0
    
    for ore_name, count in ores.items():
        if count > 0:
            price = ORE_PRICES.get(ore_name, 0)
            earned = count * price
            total_earned += earned
            total_sold += count
            inventory["ores"][ore_name] = 0
    
    if total_earned == 0:
        await callback.answer("⚠️ Нет руды для продажи!", show_alert=True)
        return
    
    user.balance += total_earned
    user.inventory = serialize_inventory(inventory)
    await session.commit()
    
    await callback.message.edit_text(
        f"💵 <b>Продажа завершена!</b>\n\n"
        f"🧱 Продано руды: {total_sold}\n"
        f"💰 Заработано: {total_earned:,}\n"
        f"💳 Баланс: {user.balance:,}",
        reply_markup=get_inventory_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer(f"Продано на {total_earned:,}💰!")


# ==================== ПЕРЕВОДЫ ====================

@router.callback_query(F.data == "transfer_menu")
async def cb_transfer_menu(callback: types.CallbackQuery, session: AsyncSession):
    """Меню переводов"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    text = (
        f"💸 <b>Перевод денег</b>\n\n"
        f"💰 Ваш баланс: {user.balance:,}\n"
        f"📥 Лимит получения: {user.transfer_limit:,}\n\n"
        f"<i>Отправьте сообщение в формате:</i>\n"
        f"<code>перевести @username сумма</code>"
    )
    
    await callback.message.edit_text(text, reply_markup=get_transfer_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.message(F.text.lower().startswith("перевести"))
async def msg_transfer(message: types.Message, session: AsyncSession):
    """Перевод денег"""
    parts = message.text.split()
    
    if len(parts) < 3:
        await message.answer("⚠️ Формат: <code>перевести @username сумма</code>", parse_mode="HTML")
        return
    
    target_username = parts[1].lstrip("@")
    try:
        amount = int(parts[2])
    except ValueError:
        await message.answer("⚠️ Сумма должна быть числом!")
        return
    
    if amount <= 0:
        await message.answer("⚠️ Сумма должна быть положительной!")
        return
    
    sender = await get_or_create_user(session, message.from_user.id)
    
    if sender.balance < amount:
        await message.answer("⚠️ Недостаточно средств!")
        return
    
    # Поиск получателя по username (в реальном боте нужен кэш или API)
    # Для демо используем заглушку
    await message.answer("⚠️ В демо-режиме переводы недоступны. Нужен кэш пользователей.")


# ==================== МАГАЗИН ====================

@router.callback_query(F.data == "shop")
async def cb_shop(callback: types.CallbackQuery, session: AsyncSession):
    """Магазин"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    pickaxe_cost = int(100 * (UPGRADES["кирка"]["base_power"] ** user.pickaxe_power))
    booster_cost = int(200 * (UPGRADES["бустер"]["base_power"] ** user.booster_power))
    
    text = (
        f"🏪 <b>Магазин</b>\n\n"
        f"💰 Ваш баланс: {user.balance:,}\n"
        f"🎆 Плазма: {user.plasma:,}\n\n"
        f"⚒️ <b>Улучшения:</b>\n"
        f"• Кирка (+×0.5): {pickaxe_cost}💰 (сейчас ×{user.pickaxe_power:.2f})\n"
        f"• Бустер (+×1.0): {booster_cost}💰 (сейчас ×{user.booster_power:.2f})\n\n"
        f"<i>Плазма требуется для некоторых улучшений!</i>"
    )
    
    await callback.message.edit_text(text, reply_markup=get_shop_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "upgrade_pickaxe")
async def cb_upgrade_pickaxe(callback: types.CallbackQuery, session: AsyncSession):
    """Улучшение кирки"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    cost = int(100 * (1.5 ** user.pickaxe_power))
    
    if user.balance < cost:
        await callback.answer(f"⚠️ Нужно {cost}💰!", show_alert=True)
        return
    
    user.balance -= cost
    user.pickaxe_power += 0.5
    await session.commit()
    
    await callback.answer(f"Кирка улучшена до ×{user.pickaxe_power:.2f}! ⚒️")
    await cb_shop(callback, session)


@router.callback_query(F.data == "buy_booster")
async def cb_buy_booster(callback: types.CallbackQuery, session: AsyncSession):
    """Покупка бустера"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    cost = int(200 * (2.0 ** user.booster_power))
    
    if user.balance < cost:
        await callback.answer(f"⚠️ Нужно {cost}💰!", show_alert=True)
        return
    
    user.balance -= cost
    user.booster_power += 1.0
    await session.commit()
    
    await callback.answer(f"Бустер улучшен до ×{user.booster_power:.2f}! 🚀")
    await cb_shop(callback, session)


# ==================== НАВИГАЦИЯ ====================

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: types.CallbackQuery, session: AsyncSession):
    """Главное меню"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    text = (
        f"👋 {user.first_name}, добро пожаловать!\n\n"
        f"💰 Баланс: {user.balance:,}\n"
        f"🎆 Плазма: {user.plasma:,}\n"
        f"📊 Уровень: {user.level}"
    )
    
    await callback.message.edit_text(text, reply_markup=get_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "close_menu")
async def cb_close_menu(callback: types.CallbackQuery):
    """Закрыть меню"""
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data == "profile")
async def cb_profile(callback: types.CallbackQuery, session: AsyncSession):
    """Профиль"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    power = calculate_power(user.pickaxe_power, user.booster_power)
    
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"📛 Имя: {user.first_name}\n"
        f"{'@' + user.username if user.username else ''}\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Уровень: {user.level}\n"
        f"• Мощность: ×{power:.2f}\n"
        f"• Баланс: {user.balance:,}💰\n"
        f"• Плазма: {user.plasma:,}🎆"
    )
    
    await callback.message.edit_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
    await callback.answer()
