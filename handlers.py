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
    get_inventory_keyboard, get_shop_keyboard, get_profile_keyboard,
    get_start_keyboard, get_sos_keyboard, get_donate_keyboard, get_back_keyboard
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


@router.message(lambda m: m.text and m.text.lower() in ["ш", "шахта"])
async def cmd_shahta(message: types.Message, session: AsyncSession):
    """Команда 'ш' или 'шахта' - меню копания"""
    user = await get_or_create_user(session, message.from_user.id)
    
    # Новичок: уровень 1, кирка 1.0, бустер 1.0 (не прокачивался)
    is_newbie = (user.level == 1 and user.pickaxe_power == 1.0 and user.booster_power == 1.0)
    
    if is_newbie:
        # Стартовые значения для новичков
        current_ore_display = "Земля I"
        power = 1.0
        case_chance = 1.0
        duration = format_time(300)
    else:
        # Данные из базы для игроков
        mine = MINES.get(user.current_mine, MINES[0])
        current_ore_display = mine["name"]
        power = calculate_power(user.pickaxe_power, user.booster_power)
        # case_chance как множитель (база 3% = ×1.0)
        case_chance = (user.case_chance or 3.0) / 3.0
        duration = format_time(user.mining_duration or BASE_MINING_TIME)
    
    text = (
        f"⛏ <b>Копание</b>\n"
        f"{'·' * 28}\n"
        f"⛰ Выбрана шахта : {current_ore_display}\n"
        f"🔥 Мощность : ×{power:.1f}\n"
        f"📦 Шанс найти кейс : ×{case_chance:.1f}\n"
        f"⏳ Время копания : {duration}\n"
        f"{'·' * 28}\n"
        f"<i>Отправься в шахту, чтобы начать добычу руды!</i>"
    )
    
    await message.answer(text, reply_markup=get_mining_menu_keyboard(), parse_mode="HTML")


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

@router.message(Command("bal"))
@router.message(lambda msg: msg.text and msg.text.lower() == "б")
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


@router.callback_query(F.data == "close_profile")
async def cb_close_profile(callback: types.CallbackQuery):
    """Закрыть профиль (удалить сообщение)"""
    await callback.message.delete()
    await callback.answer()


# ==================== ФОРМАТИРОВАНИЕ ЧИСЕЛ ====================

def format_number(num: int | float) -> str:
    """
    Форматирование больших чисел:
    1234 → 1.23K, 1234567 → 1.23M, 1234567890 → 1.23B
    10^15 → Qi, 10^18 → Sx, 10^21 → Sp, 10^24 → Oc, 10^27 → No
    10^30 → D, 10^33 → Ud, 10^36 → DD, 10^39 → Tr, 10^42 → Qad
    10^45 → Quin, 10^48 → S, 10^51 → Sept, 10^54 → O, 10^57 → N, 10^60 → Pr
    """
    if num < 1000:
        return str(int(num)) if isinstance(num, int) or num == int(num) else f"{num:.2f}"
    
    suffixes = [
        (10**60, "Pr"),   # Prata (кастомный)
        (10**57, "N"),    # Novemdecillion
        (10**54, "O"),    # Octodecillion
        (10**51, "Sept"), # Septendecillion
        (10**48, "S"),    # Sexdecillion
        (10**45, "Quin"), # Quindecillion
        (10**42, "Qad"),  # Quattuordecillion
        (10**39, "Tr"),   # Tredecillion
        (10**36, "DD"),   # Duodecillion
        (10**33, "Ud"),   # Undecillion
        (10**30, "D"),    # Decillion
        (10**27, "No"),   # Nonillion
        (10**24, "Oc"),   # Octillion
        (10**21, "Sp"),   # Septillion
        (10**18, "Sx"),   # Sextillion
        (10**15, "Qi"),   # Quintillion
        (10**12, "Qa"),   # Quadrillion
        (10**9, "B"),     # Billion
        (10**6, "M"),     # Million
        (10**3, "K"),     # Thousand
    ]
    
    for divisor, suffix in suffixes:
        if num >= divisor:
            value = num / divisor
            # Округляем до 2 знаков после запятой
            if value >= 100:
                return f"{int(value)}{suffix}"
            elif value >= 10:
                return f"{value:.1f}{suffix}"
            else:
                return f"{value:.2f}{suffix}"
    
    return str(int(num))


# ==================== ПРОФИЛЬ ====================

@router.callback_query(F.data == "profile")
async def cb_profile(callback: types.CallbackQuery, session: AsyncSession):
    """Отобразить профиль пользователя (callback)"""
    user_data = await get_or_create_user(session, callback.from_user.id)
    await _show_profile_text(callback.message, user_data, session, is_callback=True)
    await callback.answer()


@router.message(Command("profile"))
@router.message(lambda msg: msg.text and msg.text.lower() in {"профиль", "проф", "профиля"})
async def cmd_profile(message: types.Message, session: AsyncSession):
    """Отобразить профиль пользователя (команда)"""
    user_data = await get_or_create_user(session, message.from_user.id)
    await _show_profile_text(message, user_data, session, is_callback=False)


async def _show_profile_text(
    message: types.Message,
    user_data,
    session: AsyncSession,
    is_callback: bool = False
):
    """Внутренняя функция отображения профиля"""
    
    # Получаем ник
    nickname = user_data.username or user_data.first_name or "Без имени"
    
    # Получаем привилегию (по умолчанию Игрок)
    privilege = "Игрок"
    
    # Получаем клан
    clan = user_data.clan if user_data.clan else "Не в клане."
    
    # Получаем уровень кирки
    pickaxe_level = int(user_data.pickaxe_power * 2) if user_data.pickaxe_power else 1
    pickaxe_name = f"Кирка света ({pickaxe_level})"
    
    # Получаем текущую шахту
    mine = MINES.get(user_data.current_mine, MINES[0])
    current_mine = mine["name"]
    
    # Рассчитываем лимит
    limit = BASE_TRANSFER_LIMIT + (user_data.level * LIMIT_PER_LEVEL)
    limit_formatted = format_number(limit)
    
    # Получаем плазму из users
    plasma = user_data.plasma or 0
    
    # Считаем сумму всей руды в инвентаре
    result = await session.execute(
        select(Inventory).where(
            Inventory.user_id == user_data.id,
            Inventory.item_type == "ore"
        )
    )
    ores = result.scalars().all()
    total_ores = sum(item.quantity for item in ores if item.quantity > 0)
    
    # Получаем количество ударов киркой из mining_sessions
    ms_result = await session.execute(
        select(MiningSession).where(MiningSession.user_id == user_data.id)
    )
    mining_sessions = ms_result.scalars().all()
    total_strikes = sum(ms.hits or 0 for ms in mining_sessions)
    
    # Получаем убитых боссов
    bosses_defeated = len(json.loads(user_data.bosses_defeated)) if user_data.bosses_defeated else 0
    
    # Дата регистрации
    created_at = user_data.created_at
    if created_at:
        reg_date = created_at.strftime("%d-%m-%Y / %H:%M")
    else:
        reg_date = "—"
    
    # Формируем текст профиля с красивым форматированием
    # Ник в моноширинном шрифте <code> - можно скопировать по нажатию
    text = (
        f"👤 <b>Профиль</b>\n"
        f"{'·' * 30}\n"
        f"🏷 | Ник в боте: <code>{nickname}</code>\n"
        f"🔰 | Привилегия: {privilege}\n"
        f"🌟 | Уровень: {user_data.level}\n"
        f"❕ | Клан: {clan}\n"
        f"⛏️ | Инструмент: {pickaxe_name}\n"
        f"⚒️ | Выбранная шахта: {current_mine}\n"
        f"💸 | Лимит на получение: {limit_formatted}\n"
        f"💵 | Баланс: {format_number(user_data.balance)}$\n"
        f"🎆 | Плазма: {format_number(plasma)}\n"
        f"🧱 | Руды выкопано:{format_number(total_ores)} ед.\n"
        f"☠️ | Убито боссов: {bosses_defeated}\n"
        f"⛏️ | Кликков: {total_strikes:,}\n"
        f"📅 | Дата регистрации: {reg_date}"
    )
    
    if is_callback:
        await message.edit_text(text, reply_markup=get_profile_keyboard(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=get_profile_keyboard(), parse_mode="HTML")


@router.message(Command("limit"))
@router.message(lambda msg: msg.text and msg.text.lower() in {"лимит", "лим"})
async def cmd_limit(message: types.Message, session: AsyncSession):
    """Показать лимит на получение"""
    user_data = await get_or_create_user(session, message.from_user.id)
    
    limit = BASE_TRANSFER_LIMIT + (user_data.level * LIMIT_PER_LEVEL)
    received = user_data.received_today or 0
    available = limit - received
    
    text = (
        f"💸 <b>Лимит на получение</b>\n"
        f"{'·' * 30}\n"
        f"📊 Уровень:           {user_data.level}\n"
        f"💰 Лимит:             {format_number(limit)}\n"
        f"📥 Получено сегодня:  {format_number(received)}\n"
        f"✅ Доступно:          {format_number(available)}"
    )
    
    await message.answer(text, parse_mode="HTML")


# ==================== МЕНЮ (3 основных меню) ====================

@router.message(CommandStart())
async def cmd_start_menu(message: types.Message, session: AsyncSession):
    """Команда /start - Главное меню"""
    user = await get_or_create_user(session, message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    text = (
        f"👋 *Привет, {user.first_name}!*\n\n"
        f"*Основные команды:*\n"
        f"Отобразить это сообщение /start\n"
        f"Помощь по боту - `помощь`\n"
        f"Профиль - `профиль`\n"
        f"Донат - `донат`\n"
        f"Прочее - `прочее`\n"
        f"Пропала клавиатура - `старт`\n\n"
        f"[🤗 Добавить бота в группу!](https://t.me/evobanbot?startgroup=true)"
    )
    await message.answer(text, reply_markup=get_start_keyboard(), parse_mode="Markdown")


@router.message(lambda msg: msg.text and msg.text.lower() == "старт")
async def cmd_restart_keyboard(message: types.Message, session: AsyncSession):
    """Кнопка Старт - вернуть клавиатуру"""
    user = await get_or_create_user(session, message.from_user.id)
    
    text = (
        f"👋 *Привет, {user.first_name}!*\n\n"
        f"*Основные команды:*\n"
        f"Отобразить это сообщение /start\n"
        f"Помощь по боту - `помощь`\n"
        f"Профиль - `профиль`\n"
        f"Донат - `донат`\n"
        f"Прочее - `прочее`\n"
        f"Пропала клавиатура - `старт`\n\n"
        f"[🤗 Добавить бота в группу!](https://t.me/evobanbot?startgroup=true)"
    )
    await message.answer(text, reply_markup=get_start_keyboard(), parse_mode="Markdown")


@router.message(lambda msg: msg.text and msg.text.lower() == "помощь")
async def cmd_help_sos(message: types.Message, session: AsyncSession):
    """Кнопка Помощь - Меню SOS"""
    text = (
        f"🆘 *Выбери, какая помощь тебе нужна:*\n\n"
        f"💬 | Игровой чат: [@evobanchat](https://t.me/evobanchat)\n"
        f"📢 | Новостной канал: [@evo_ban_news](https://t.me/evo_ban_news)\n"
        f"🛰️ | Связь: [@Sharik_Ez](https://t.me/Sharik_Ez)"
    )
    await message.answer(text, reply_markup=get_sos_keyboard(), parse_mode="Markdown")


@router.message(lambda msg: msg.text and msg.text.lower() == "донат")
async def cmd_donate_menu(message: types.Message, session: AsyncSession):
    """Кнопка Донат - Меню Донатик"""
    user = await get_or_create_user(session, message.from_user.id)
    
    text = (
        f"💰 *Донатик*\n"
        f"{'·' * 28}\n"
        f"*Здесь ты можешь ознакомиться с игровыми бонусами...*\n"
        f"💳 *Баланс : {user.balance} Эво-Коинов*\n"
        f"*Выбери раздел по кнопке ниже:*"
    )
    await message.answer(text, reply_markup=get_donate_keyboard(), parse_mode="Markdown")


@router.message(lambda msg: msg.text and msg.text.lower() == "профиль")
async def cmd_profile_menu(message: types.Message, session: AsyncSession):
    """Кнопка Профиль - показать профиль"""
    user_data = await get_or_create_user(session, message.from_user.id)
    await _show_profile_text(message, user_data, session, is_callback=False)


@router.message(lambda msg: msg.text and msg.text.lower() == "прочее")
async def cmd_other_menu(message: types.Message, session: AsyncSession):
    """Кнопка Прочее"""
    text = (
        f"📂 *Прочее*\n\n"
        f"*Раздел в разработке...*\n\n"
        f"Здесь будут дополнительные функции."
    )
    await message.answer(text, reply_markup=get_back_keyboard(), parse_mode="Markdown")


# ==================== CALLBACK ДЛЯ МЕНЮ ====================

@router.callback_query(F.data == "back_to_start")
async def cb_back_to_start(callback: types.CallbackQuery):
    """Кнопка Назад в главное меню"""
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data.startswith("help_"))
async def cb_help_sections(callback: types.CallbackQuery):
    """Обработчик кнопок меню помощи"""
    section = callback.data.replace("help_", "")
    
    help_texts = {
        "howto": "📚 *Как играть?*\n\n1. Нажмите ⛏️ Добывать\n2. Ждите завершения таймера\n3. Соберите ресурсы\n4. Продавайте руду в инвентаре",
        "commands": "✏️ *Команды бота:*\n\n/start - Главное меню\n/profile - Профиль\n/bal - Баланс\n/inv - Инвентарь\n/lvl - Уровень",
        "rules": "📄 *Правила проекта:*\n\n1. Уважайте других игроков\n2. Запрещён читинг\n3. Следуйте правилам чата",
        "faq": "❓ *Частые вопросы:*\n\n*Как добыть руду?*\n- Запустите добычу и дождитесь завершения\n\n*Как продать руду?*\n- Инвентарь → Продать всю руду",
        "clans": "🏰 *Кланы*\n\nФункция в разработке...\n\nСоздавайте кланы и играйте вместе!",
        "admin": "🛡️ *Администрирование чата*\n\nБот умеет модерировать чат.\n\nДобавьте бота в группу как администратора.",
        "donate": "💰 *Донат*\n\nПоддержите проект и получите бонусы!\n\nНажмите /donate или кнопку Донат",
    }
    
    text = help_texts.get(section, "ℹ️ Раздел в разработке...")
    await callback.message.answer(text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("donate_"))
async def cb_donate_sections(callback: types.CallbackQuery):
    """Обработчик кнопок меню доната"""
    section = callback.data.replace("donate_", "")
    
    if section == "close":
        await callback.message.delete()
        await callback.answer()
        return
    elif section == "topup":
        text = (
            "💳 *Пополнение баланса*\n\n"
            "Выберите способ оплаты:\n"
            "• 💎 Stars\n"
            "• 📱 ЮMoney\n"
            "• 💳 Карта\n\n"
            "*Скоро доступно...*"
        )
        await callback.message.answer(text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    elif section == "bundle":
        text = (
            "💥 *Бандл*\n\n"
            "Выгодный набор бонусов!\n\n"
            "• ×2 Кирка\n"
            "• ×2 Бустер\n"
            "• 1000 Эво-Коинов\n\n"
            "*Цена: 299₽*"
        )
        await callback.message.answer(text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    else:
        # donate_1, donate_2, donate_3, donate_4
        text = f"⚜️ *Бонус {section.upper()}*\n\n*В разработке...*"
        await callback.message.answer(text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    
    await callback.answer()
