"""Обработчики команд для AFK-добычи (одна руда на шахту)"""
import random
import json
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, types, Bot
from aiogram.filters import Command, CommandStart
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)

from config import (
    MINES, ORE_PRICES, PLASMA_CHANCE, CASE_CHANCE,
    BASE_MINING_TIME, FLOOD_WAIT_WARN, CASE_TYPES,
    BASE_TRANSFER_LIMIT, LIMIT_PER_LEVEL, BOSS_LEVELS
)
from database import get_or_create_user, MiningSession, Inventory
from keyboards import (
    get_mining_menu_keyboard, get_mines_keyboard, get_main_menu_keyboard,
    get_inventory_keyboard, get_shop_keyboard
)

router = Router()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_available_mines(level: int) -> dict:
    """Получить доступные шахты"""
    return {mid: mdata for mid, mdata in MINES.items() if level >= mdata["level_req"]}


def calculate_power(pickaxe: float, booster: float) -> float:
    """Расчёт мощности"""
    return pickaxe * booster


def get_ore_name(mine_id: int) -> str:
    """Получить название руды для шахты"""
    if mine_id not in MINES:
        return "земля"
    return MINES[mine_id]["ore"]


def get_random_case() -> str:
    """Случайный кейс"""
    return random.choice(CASE_TYPES)


def format_time(seconds: int) -> str:
    """Форматирование времени"""
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins}м. {secs}с."


def check_level_up(current_exp: int, level: int) -> tuple[int, int, bool]:
    """Проверка уровня"""
    exp_needed = level * 100
    if current_exp >= exp_needed:
        return current_exp - exp_needed, level + 1, True
    return current_exp, level, False


async def get_or_create_session(session: AsyncSession, user_id: int) -> MiningSession:
    """Получить или создать сессию"""
    result = await session.execute(select(MiningSession).where(MiningSession.user_id == user_id))
    ms = result.scalar_one_or_none()
    
    if not ms:
        ms = MiningSession(user_id=user_id)
        session.add(ms)
        await session.commit()
        await session.refresh(ms)
    
    return ms


async def get_inventory_item(session: AsyncSession, user_id: int, item_type: str, item_name: str) -> Inventory | None:
    """Получить предмет из инвентаря"""
    result = await session.execute(
        select(Inventory).where(
            Inventory.user_id == user_id,
            Inventory.item_type == item_type,
            Inventory.item_name == item_name
        )
    )
    return result.scalar_one_or_none()


async def add_to_inventory(session: AsyncSession, user_id: int, item_type: str, item_name: str, quantity: int):
    """Добавить в инвентарь"""
    if quantity <= 0:
        return
    
    inv_item = await get_inventory_item(session, user_id, item_type, item_name)
    
    if inv_item:
        inv_item.quantity += quantity
        inv_item.updated_at = datetime.utcnow()
    else:
        inv_item = Inventory(user_id=user_id, item_type=item_type, item_name=item_name, quantity=quantity)
        session.add(inv_item)
    
    await session.commit()


async def accumulate_plasma_and_cases(ms: MiningSession, plasma_chance: float) -> tuple[int, int, list]:
    """
    Накопить плазму и кейсы за прошедшее время с last_update.
    Плазма НАКАПЛИВАЕТСЯ: каждую 1 секунду → если random() < plasma_chance → plasma_dug += 1
    Возвращает: (новые удары, новая плазма, новые кейсы)
    """
    if not ms.last_update or not ms.is_active:
        return 0, 0, []
    
    now = datetime.utcnow()
    elapsed_seconds = int((now - ms.last_update).total_seconds())
    elapsed_seconds = max(0, elapsed_seconds)
    
    if elapsed_seconds == 0:
        return 0, 0, []
    
    # Накопление плазмы и кейсов за прошедшие секунды
    new_plasma = 0
    new_cases = []
    
    for _ in range(elapsed_seconds):
        if random.random() * 100 < plasma_chance:
            new_plasma += 1
        if random.random() * 100 < CASE_CHANCE:
            new_cases.append(get_random_case())
    
    return elapsed_seconds, new_plasma, new_cases


async def mining_finished_by_time(message: types.Message, session: AsyncSession, user, ms: MiningSession):
    """Отправить НОВОЕ сообщение о завершении по таймеру (🔔 вариант) - при ручном обновлении"""
    from keyboards import get_mining_finished_keyboard
    
    hits = ms.hits or 0
    ores = ms.ores_dug or 0
    plasma = ms.plasma_dug or 0
    
    # Сохраняем в сессию пользователя для последующего сбора
    user.session_hits = hits
    user.session_ores = ores
    user.session_plasma = plasma
    user.session_cases = ms.cases_found or 0
    await session.commit()
    
    # ОТПРАВЛЯЕМ НОВОЕ сообщение с 🔔 (время закончилось)
    text = (
        f"🔔 **Копание завершено!**\n"
        f"{'.' * 30}\n"
        f"*Собери ресурсы, чтобы начать добычу заново!*"
    )
    
    await message.answer(text, reply_markup=get_mining_finished_keyboard(), parse_mode="HTML")


async def send_mining_finished_notification(bot: Bot, session: AsyncSession, ms: MiningSession):
    """Отправить авто-уведомление от бота когда время копания заканчивается (⛏️ вариант)
    Вызывается из фоновой задачи mining_timer_task
    """
    from aiogram.exceptions import TelegramForbiddenError
    from keyboards import get_collect_completed_keyboard
    
    # Получаем пользователя
    from database import get_or_create_user
    user = await get_or_create_user(session, ms.user_id)
    
    hits = ms.hits or 0
    ores = ms.ores_dug or 0
    plasma = ms.plasma_dug or 0
    cases_count = ms.cases_found or 0
    
    # Сохраняем в сессию пользователя для последующего сбора
    user.session_hits = hits
    user.session_ores = ores
    user.session_plasma = plasma
    user.session_cases = cases_count
    user.is_mining = False
    ms.is_active = False
    await session.commit()
    
    # Формируем текст как при само-остановке (⛏️ меню)
    mine = MINES.get(user.current_mine, MINES[0])
    ore_name = mine["ore"].capitalize()
    
    text = (
        f"⛏️ **Копание завершено!**\n"
        f"{'.' * 30}\n"
        f"⛰️ Шахта : {ms.mine_name or mine['name']}\n"
        f"⏳ Время копания : {hits}с.\n"
        f"{'.' * 30}\n"
        f"⛏️ Удары киркой : {hits}\n"
        f"🧱 Руды добыто : {ores:,}\n"
        f"🎆 Плазмы добыто : {plasma}\n"
        f"📦 Кейсы: {cases_count}"
    )
    
    try:
        # Отправляем уведомление через bot.send_message
        await bot.send_message(
            chat_id=ms.chat_id,
            text=text,
            reply_markup=get_collect_completed_keyboard(),
            parse_mode="HTML"
        )
    except TelegramForbiddenError:
        logger.warning(f"⚠️ Пользователь {ms.user_id} заблокировал бота")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления пользователю {ms.user_id}: {e}")


# ==================== КОМАНДЫ ====================

@router.message(CommandStart())
async def cmd_start(message: types.Message, session: AsyncSession):
    """Старт"""
    user = await get_or_create_user(session, message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "🎮 <b>Mining Bot - AFK добыча руды</b>\n\n"
        "📜 <b>Как играть:</b>\n"
        "• ⛏️ Каждая шахта добывает свою руду\n"
        "• 💰 1 сек = 1 удар, руда = мощность × удары\n"
        "• 🎆 Плазма: 5% за удар\n"
        "• 📦 Кейсы: 3% за удар\n"
        "• 🧱 Собирай после остановки\n\n"
        "Используй кнопки ниже!"
    )
    await message.answer(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
    

@router.message(Command("bal") | F.text.lower() == "б")
async def cmd_balance(message: types.Message, session: AsyncSession):
    """Баланс"""
    user = await get_or_create_user(session, message.from_user.id)
    text = f"💰 <b>Баланс</b>\n\n💵 {user.balance:,}\n🎆 {user.plasma:,}\n📊 ур. {user.level}"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("inv"))
async def cmd_inventory(message: types.Message, session: AsyncSession):
    """Инвентарь"""
    user = await get_or_create_user(session, message.from_user.id)
    result = await session.execute(select(Inventory).where(Inventory.user_id == user.id).order_by(Inventory.item_name))
    items = result.scalars().all()
    
    text = "🎒 <b>Инвентарь</b>\n\n"
    if not items:
        text += "📭 Пусто"
    else:
        for item in items:
            if item.quantity > 0:
                if item.item_type == "ore":
                    price = ORE_PRICES.get(item.item_name, 0)
                    text += f"⛏️ {item.item_name.capitalize()}: {item.quantity:,} ({price}💰)\n"
                elif item.item_type == "case":
                    text += f"📦 {item.item_name.capitalize()}: {item.quantity}\n"
    
    await message.answer(text, reply_markup=get_inventory_keyboard(), parse_mode="HTML")


@router.message(Command("lvl"))
async def cmd_level(message: types.Message, session: AsyncSession):
    """Уровень"""
    user = await get_or_create_user(session, message.from_user.id)
    mine = MINES.get(user.current_mine, MINES[0])
    ore_name = mine["ore"].capitalize()
    power = calculate_power(user.pickaxe_power, user.booster_power)
    
    text = (
        f"📈 <b>Уровень {user.level}</b>\n\n"
        f"⚒️ Кирка: ×{user.pickaxe_power:.2f}\n"
        f"🚀 Бустер: ×{user.booster_power:.2f}\n"
        f"💪 Мощность: ×{power:.2f}\n"
        f"🎆 Шанс плазмы: {user.plasma_chance:.1f}%\n\n"
        f"⛰️ Шахта: {mine['name']}\n"
        f"🧱 Руда: {ore_name}"
    )
    await message.answer(text, parse_mode="HTML")


# ==================== ДОБЫЧА ====================

@router.callback_query(F.data == "mining_menu")
async def cb_mining_menu(callback: types.CallbackQuery, session: AsyncSession):
    """Меню добычи"""
    user = await get_or_create_user(session, callback.from_user.id)
    ms = await get_or_create_session(session, user.id)
    
    mine = MINES.get(user.current_mine, MINES[0])
    mine_name = mine["name"]
    ore_name = mine["ore"].capitalize()
    power = calculate_power(user.pickaxe_power, user.booster_power)
    now = datetime.utcnow()
    
    if user.is_mining and ms.is_active and ms.end_time and now < ms.end_time:
        # Показываем ТОЛЬКО накопленные значения из БД (не пересчитывать!)
        hits = ms.hits or 0
        ores = ms.ores_dug or 0
        plasma = ms.plasma_dug or 0
        cases_count = ms.cases_found or 0
        
        flood_warn = ""
        if ms.last_update and (now - ms.last_update).total_seconds() < FLOOD_WAIT_WARN:
            flood_warn = f"\n\n❗️ Не обновляй чаще 2-3 мин (flood wait), но кнопка работает!"
        
        text = (
            f"⛏️ <b>Вы копаете</b>\n\n"
            f"{'.' * 30}\n"
            f"⛰️ Шахта: {mine_name}\n"
            f"🧱 Руда: {ore_name}\n"
            f"🔥 Мощность: ×{power:.2f}\n"
            f"{'.' * 30}\n"
            f"⛏️ Удары: {hits}\n"
            f"🧱 {ore_name}: {ores:,}\n"
            f"🎆 Плазма: {plasma}\n"
            f"📦 Кейсы: {cases_count}\n"
            f"{'.' * 30}\n"
            f"⏳ Осталось: {format_time(int((ms.end_time - now).total_seconds()))}"
            f"{flood_warn}"
        )
        await callback.message.edit_text(text, reply_markup=get_mining_menu_keyboard(is_mining=True, mining_active=True), parse_mode="HTML")
        
    elif user.is_mining and ms.is_active:
        # Время вышло — сначала накопим плазму за прошедшее время
        elapsed, new_plasma, new_cases = await accumulate_plasma_and_cases(ms, user.plasma_chance)
        
        if elapsed > 0:
            ms.plasma_dug = (ms.plasma_dug or 0) + new_plasma
            existing_cases = json.loads(ms.cases_list) if ms.cases_list else []
            all_cases = existing_cases + new_cases
            ms.cases_list = json.dumps(all_cases)
            ms.cases_found = len(all_cases)
            ms.hits = (ms.hits or 0) + elapsed
            power = calculate_power(user.pickaxe_power, user.booster_power)
            ms.ores_dug = int(ms.hits * power)
        
        # Теперь используем накопленные значения
        hits = ms.hits or 0
        ores = ms.ores_dug or 0
        plasma = ms.plasma_dug or 0
        cases_count = ms.cases_found or 0
        
        ms.hits = hits
        ms.ores_dug = ores
        ms.plasma_dug = plasma
        ms.cases_found = cases_count
        ms.is_active = False
        user.is_mining = False
        user.session_hits = hits
        user.session_ores = ores
        user.session_plasma = plasma
        user.session_cases = cases_count
        await session.commit()
        
        # Отправляем НОВОЕ сообщение с 🔔 через вспомогательную функцию
        await mining_finished_by_time(callback.message, session, user, ms)
        
    else:
        text = (
            f"⛏️ <b>Копание</b>\n\n"
            f"{'.' * 30}\n"
            f"⛰️ Шахта: {mine_name}\n"
            f"🧱 Руда: {ore_name}\n"
            f"🔥 Мощность: ×{power:.2f}\n"
            f"⏳ Время: {format_time(BASE_MINING_TIME)}\n"
            f"{'.' * 30}\n"
            f"<i>Нажми 🔨 Добывать!</i>"
        )
        await callback.message.edit_text(text, reply_markup=get_mining_menu_keyboard(), parse_mode="HTML")
    
    await callback.answer()


@router.callback_query(F.data == "start_mining")
async def cb_start_mining(callback: types.CallbackQuery, session: AsyncSession):
    """Начать добычу"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    if user.is_mining:
        await callback.answer("⚠️ Уже копаете!", show_alert=True)
        return
    
    now = datetime.utcnow()
    end_time = now + timedelta(seconds=BASE_MINING_TIME)
    mine = MINES.get(user.current_mine, MINES[0])
    ore_name = mine["ore"]
    
    user.is_mining = True
    user.mining_start = now
    user.mining_end = end_time
    user.last_update = now
    
    ms = await get_or_create_session(session, user.id)
    ms.mine_id = user.current_mine
    ms.mine_name = mine["name"]
    ms.ore_name = ore_name
    ms.power = calculate_power(user.pickaxe_power, user.booster_power)
    ms.start_time = now
    ms.end_time = end_time
    ms.hits = 0
    ms.ores_dug = 0
    ms.plasma_dug = 0
    ms.cases_found = 0
    ms.cases_list = json.dumps([])
    ms.is_active = True
    ms.last_update = now
    ms.chat_id = callback.message.chat.id  # Сохраняем chat_id для уведомления
    ms.notification_sent = False  # Сбрасываем флаг уведомления
    
    await session.commit()
    
    await callback.message.edit_text(
        f"⛏️ <b>Добыча началась!</b>\n\n🧱 {ore_name.capitalize()}\n⏳ {format_time(BASE_MINING_TIME)}",
        reply_markup=get_mining_menu_keyboard(is_mining=True, mining_active=True),
        parse_mode="HTML"
    )
    await callback.answer("🎉 Поехали!")


@router.callback_query(F.data == "update_mining")
async def cb_update_mining(callback: types.CallbackQuery, session: AsyncSession):
    """Обновить (всегда доступно)
    Плазма НАКАПЛИВАЕТСЯ: каждую 1 секунду → если random() < plasma_chance → plasma_dug += 1
    """
    user = await get_or_create_user(session, callback.from_user.id)
    ms = await get_or_create_session(session, user.id)
    
    if not user.is_mining or not ms.is_active:
        await callback.answer("⚠️ Не копаете!", show_alert=True)
        return
    
    now = datetime.utcnow()
    if ms.end_time and now >= ms.end_time:
        ms.is_active = False
        user.is_mining = False
        await session.commit()
        await callback.answer("⏰ Время вышло!")
        # Отправляем НОВОЕ сообщение с 🔔 вместо редактирования
        await mining_finished_by_time(callback.message, session, user, ms)
        return
    
    # Накопление плазмы и кейсов за прошедшее время
    elapsed, new_plasma, new_cases = await accumulate_plasma_and_cases(ms, user.plasma_chance)
    
    if elapsed > 0:
        # Обновляем накопленные значения
        ms.plasma_dug = (ms.plasma_dug or 0) + new_plasma
        
        # Добавляем новые кейсы к существующим
        existing_cases = json.loads(ms.cases_list) if ms.cases_list else []
        all_cases = existing_cases + new_cases
        ms.cases_list = json.dumps(all_cases)
        ms.cases_found = len(all_cases)
        
        # Обновляем hits и ores_dug
        power = calculate_power(user.pickaxe_power, user.booster_power)
        ms.hits = (ms.hits or 0) + elapsed
        ms.ores_dug = int(ms.hits * power)
    
    ms.last_update = now
    user.last_update = now
    await session.commit()
    
    await cb_mining_menu(callback, session)
    await callback.answer("🔄")


@router.callback_query(F.data == "stop_mining")
async def cb_stop_mining(callback: types.CallbackQuery, session: AsyncSession):
    """Остановить (само-остановка через кнопку 🚫)"""
    user = await get_or_create_user(session, callback.from_user.id)
    ms = await get_or_create_session(session, user.id)
    
    if not user.is_mining or not ms.is_active:
        await callback.answer("⚠️ Не копаете!", show_alert=True)
        return
    
    now = datetime.utcnow()
    
    # Сначала накопим плазму за прошедшее время
    elapsed, new_plasma, new_cases = await accumulate_plasma_and_cases(ms, user.plasma_chance)
    
    if elapsed > 0:
        ms.plasma_dug = (ms.plasma_dug or 0) + new_plasma
        existing_cases = json.loads(ms.cases_list) if ms.cases_list else []
        all_cases = existing_cases + new_cases
        ms.cases_list = json.dumps(all_cases)
        ms.cases_found = len(all_cases)
        ms.hits = (ms.hits or 0) + elapsed
        power = calculate_power(user.pickaxe_power, user.booster_power)
        ms.ores_dug = int(ms.hits * power)
    
    ms.is_active = False
    ms.end_time = now
    user.is_mining = False
    
    # Используем накопленные значения
    hits = ms.hits or 0
    ores = ms.ores_dug or 0
    plasma = ms.plasma_dug or 0
    cases_count = ms.cases_found or 0
    
    ms.hits = hits
    ms.ores_dug = ores
    ms.plasma_dug = plasma
    ms.cases_found = cases_count
    
    user.session_hits = hits
    user.session_ores = ores
    user.session_plasma = plasma
    user.session_cases = cases_count
    
    await session.commit()
    await callback.answer("⏹️ Остановлено")
    
    # ЗАМЕНЯЕМ сообщение на ⛏️ вариант
    mine = MINES.get(user.current_mine, MINES[0])
    ore_name = mine["ore"].capitalize()
    
    text = (
        f"⛏️ **Копание завершено!**\n"
        f"{'.' * 30}\n"
        f"⛰️ Шахта : {ms.mine_name or mine['name']}\n"
        f"⏳ Время копания : {hits}с.\n"
        f"{'.' * 30}\n"
        f"⛏️ Удары киркой : {hits}\n"
        f"🧱 Руды добыто : {ores}\n"
        f"🎆 Плазмы добыто : {plasma}"
    )
    
    # Кнопки: Собрать (широкая синяя), Закрыть (широкая синяя)
    from keyboards import get_collect_completed_keyboard
    await callback.message.edit_text(text, reply_markup=get_collect_completed_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "collect_from_notification")
async def cb_collect_from_notification(callback: types.CallbackQuery, session: AsyncSession):
    """Собрать из уведомления (когда время закончилось) - показывает то же меню как при само-остановке"""
    user = await get_or_create_user(session, callback.from_user.id)
    ms = await get_or_create_session(session, user.id)
    
    # Используем накопленные значения из сессии майнинга
    hits = ms.hits or 0
    ores = ms.ores_dug or 0
    plasma = ms.plasma_dug or 0
    
    mine = MINES.get(user.current_mine, MINES[0])
    
    text = (
        f"⛏️ **Копание завершено!**\n"
        f"{'.' * 30}\n"
        f"⛰️ Шахта : {ms.mine_name or mine['name']}\n"
        f"⏳ Время копания : {hits}с.\n"
        f"{'.' * 30}\n"
        f"⛏️ Удары киркой : {hits}\n"
        f"🧱 Руды добыто : {ores}\n"
        f"🎆 Плазмы добыто : {plasma}"
    )
    
    from keyboards import get_collect_completed_keyboard
    await callback.message.edit_text(text, reply_markup=get_collect_completed_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "collect_resources")
async def cb_collect_resources(callback: types.CallbackQuery, session: AsyncSession):
    """Собрать"""
    user = await get_or_create_user(session, callback.from_user.id)
    ms = await get_or_create_session(session, user.id)
    
    if user.session_ores <= 0:
        await callback.answer("⚠️ Пусто!", show_alert=True)
        return
    
    ore_name = ms.ore_name or MINES.get(user.current_mine, MINES[0])["ore"]
    ores_collected = user.session_ores
    plasma_collected = user.session_plasma
    cases_list = json.loads(ms.cases_list) if ms.cases_list else []
    
    # Добавляем руду
    await add_to_inventory(session, user.id, "ore", ore_name, ores_collected)
    
    # Плазма
    user.plasma += plasma_collected
    
    # Кейсы
    for case in cases_list:
        await add_to_inventory(session, user.id, "case", case, 1)
    
    # Опыт
    exp = ores_collected // 10
    if exp > 0:
        user.experience += exp
        new_exp, new_lvl, up = check_level_up(user.experience, user.level)
        user.experience = new_exp
        user.level = new_lvl
        if up:
            user.transfer_limit = BASE_TRANSFER_LIMIT + (new_lvl * LIMIT_PER_LEVEL)
    
    # Сброс
    ms.hits = 0
    ms.ores_dug = 0
    ms.plasma_dug = 0
    ms.cases_found = 0
    ms.cases_list = json.dumps([])
    ms.is_active = False
    ms.start_time = None
    ms.end_time = None
    
    user.session_hits = 0
    user.session_ores = 0
    user.session_plasma = 0
    user.session_cases = 0
    user.mining_start = None
    user.mining_end = None
    
    await session.commit()
    
    text = f"🧱 <b>Собрано!</b>\n\n{ore_name.capitalize()}: {ores_collected:,}\n🎆 {plasma_collected}\n📦 {len(cases_list)}\n⭐ +{exp}"
    await callback.message.edit_text(text, reply_markup=get_mining_menu_keyboard(), parse_mode="HTML")
    await callback.answer("🎒 В инвентарь!")


@router.callback_query(F.data.startswith("select_mine_"))
async def cb_select_mine(callback: types.CallbackQuery, session: AsyncSession):
    """Выбрать шахту"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    if user.is_mining:
        await callback.answer("⚠️ Завершите добычу!", show_alert=True)
        return
    
    mine_id = int(callback.data.split("_")[-1])
    if mine_id not in MINES or user.level < MINES[mine_id]["level_req"]:
        await callback.answer("⚠️ Нельзя!", show_alert=True)
        return
    
    user.current_mine = mine_id
    await session.commit()
    await callback.answer(f"✅ {MINES[mine_id]['name']}")
    await cb_mining_menu(callback, session)


# ==================== ИНВЕНТАРЬ И ПРОДАЖА ====================

@router.callback_query(F.data == "inventory")
async def cb_inventory(callback: types.CallbackQuery, session: AsyncSession):
    """Инвентарь"""
    user = await get_or_create_user(session, callback.from_user.id)
    result = await session.execute(select(Inventory).where(Inventory.user_id == user.id).order_by(Inventory.item_name))
    items = result.scalars().all()
    
    text = "🎒 <b>Инвентарь</b>\n\n"
    if not items:
        text += "📭 Пусто"
    else:
        for item in items:
            if item.quantity > 0:
                if item.item_type == "ore":
                    price = ORE_PRICES.get(item.item_name, 0)
                    text += f"⛏️ {item.item_name.capitalize()}: {item.quantity:,} ({price}💰)\n"
                elif item.item_type == "case":
                    text += f"📦 {item.item_name.capitalize()}: {item.quantity}\n"
    
    await callback.message.edit_text(text, reply_markup=get_inventory_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "sell_all_ores")
async def cb_sell_all(callback: types.CallbackQuery, session: AsyncSession):
    """Продать всё"""
    user = await get_or_create_user(session, callback.from_user.id)
    result = await session.execute(select(Inventory).where(Inventory.user_id == user.id, Inventory.item_type == "ore"))
    ores = result.scalars().all()
    
    total = 0
    count = 0
    for ore in ores:
        if ore.quantity > 0:
            price = ORE_PRICES.get(ore.item_name, 0)
            total += ore.quantity * price
            count += ore.quantity
            ore.quantity = 0
    
    if total == 0:
        await callback.answer("⚠️ Нет руды!", show_alert=True)
        return
    
    user.balance += total
    await session.commit()
    
    await callback.message.edit_text(
        f"💵 <b>Продано!</b>\n\n🧱 {count:,}\n💰 {total:,}\n💳 {user.balance:,}",
        reply_markup=get_inventory_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer(f"💰 +{total:,}")


# ==================== НАВИГАЦИЯ ====================

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: types.CallbackQuery, session: AsyncSession):
    """Главное меню"""
    user = await get_or_create_user(session, callback.from_user.id)
    text = f"👋 {user.first_name}\n\n💰 {user.balance:,}\n🎆 {user.plasma:,}\n📊 ур. {user.level}"
    await callback.message.edit_text(text, reply_markup=get_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "close_menu")
async def cb_close_menu(callback: types.CallbackQuery):
    """Закрыть"""
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data == "shop")
async def cb_shop(callback: types.CallbackQuery, session: AsyncSession):
    """Магазин"""
    user = await get_or_create_user(session, callback.from_user.id)
    pick_cost = int(100 * (1.5 ** user.pickaxe_power))
    boost_cost = int(200 * (2.0 ** user.booster_power))
    
    text = (
        f"🏪 <b>Магазин</b>\n\n"
        f"💰 {user.balance:,} | 🎆 {user.plasma:,}\n\n"
        f"⚒️ Кирка +0.5: {pick_cost}💰 (сейчас ×{user.pickaxe_power:.2f})\n"
        f"🚀 Бустер +1.0: {boost_cost}💰 (сейчас ×{user.booster_power:.2f})"
    )
    await callback.message.edit_text(text, reply_markup=get_shop_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "upgrade_pickaxe")
async def cb_upgrade_pickaxe(callback: types.CallbackQuery, session: AsyncSession):
    """Улучшить кирку"""
    user = await get_or_create_user(session, callback.from_user.id)
    cost = int(100 * (1.5 ** user.pickaxe_power))
    
    if user.balance < cost:
        await callback.answer(f"⚠️ Нужно {cost}💰!", show_alert=True)
        return
    
    user.balance -= cost
    user.pickaxe_power += 0.5
    await session.commit()
    await callback.answer(f"⚒️ Кирка ×{user.pickaxe_power:.2f}!")
    await cb_shop(callback, session)


@router.callback_query(F.data == "buy_booster")
async def cb_buy_booster(callback: types.CallbackQuery, session: AsyncSession):
    """Бустер"""
    user = await get_or_create_user(session, callback.from_user.id)
    cost = int(200 * (2.0 ** user.booster_power))
    
    if user.balance < cost:
        await callback.answer(f"⚠️ Нужно {cost}💰!", show_alert=True)
        return
    
    user.balance -= cost
    user.booster_power += 1.0
    await session.commit()
    await callback.answer(f"🚀 Бустер ×{user.booster_power:.2f}!")
    await cb_shop(callback, session)
