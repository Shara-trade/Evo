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
from database import get_or_create_user, get_or_create_user_settings, toggle_notifications, MiningSession, Inventory
from keyboards import (
    get_mining_menu_keyboard, get_mines_keyboard, get_main_menu_keyboard,
    get_inventory_keyboard, get_shop_keyboard, get_profile_keyboard,
    get_start_keyboard, get_sos_keyboard, get_donate_keyboard, get_back_keyboard,
    get_mining_finished_keyboard, get_collect_completed_keyboard,
    get_subscription_keyboard
)
from channel_check import check_channel_subscription

router = Router()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_available_mines(level: int) -> dict:
    """Получить доступные шахты"""
    return {mid: mdata for mid, mdata in MINES.items() if level >= mdata["level_req"]}


def calculate_power(pickaxe: float, booster: float, mining_bonus: float = 1.0) -> float:
    """Расчёт мощности с учётом бонуса за подписку"""
    return pickaxe * booster * mining_bonus


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


async def apply_mining_bonus(session: AsyncSession, user, bot: Bot) -> bool:
    """
    Проверить подписку на канал и выдать бонус, если пользователь подписан.
    
    Returns:
        True если бонус был выдан (или уже был), False если пользователь не подписан.
    """
    # Если бонус уже выдан — ничего не делаем
    if user.channel_subscribed:
        return True
    
    # Проверяем подписку
    is_subscribed = await check_channel_subscription(bot, user.id)
    
    if is_subscribed:
        # Выдаём бонус
        user.mining_bonus = 1.5
        user.channel_subscribed = True
        await session.commit()
        return True
    else:
        return False


@router.message(lambda m: m.text and m.text.lower() in ["ш", "шахта"])
async def cmd_shahta(message: types.Message, session: AsyncSession):
    """Команда 'ш' или 'шахта' - меню копания"""
    user = await get_or_create_user(session, message.from_user.id)
    
    # Проверяем подписку и выдаём бонус (если ещё не выдан)
    from bot import _bot_instance
    if _bot_instance and not user.channel_subscribed:
        is_subscribed = await check_channel_subscription(_bot_instance, user.id)
        if is_subscribed:
            user.mining_bonus = 1.5
            user.channel_subscribed = True
            await session.commit()
    
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
        power = calculate_power(user.pickaxe_power, user.booster_power, user.mining_bonus or 1.0)
        # case_chance как множитель (база 3% = ×1.0)
        case_chance = (user.case_chance or 3.0) / 3.0
        duration = format_time(user.mining_duration or BASE_MINING_TIME)
    
    text = (
        f"⛏ <b>Копание</b>\n"
        f"{'·' * 28}\n"
        f"⛰ Выбрана шахта : {current_ore_display}\n"
        f"🔥 Мощность : ×{power:.1f}" + (f" (включая бонус ×{user.mining_bonus:.1f})" if user.mining_bonus and user.mining_bonus > 1.0 else "") + "\n"
        f"📦 Шанс найти кейс : ×{case_chance:.1f}\n"
        f"⏳ Время копания : {duration}\n"
        f"{'·' * 28}\n"
        f"<i>Отправься в шахту, чтобы начать добычу руды!</i>"
    )
    
    await message.answer(text, reply_markup=get_mining_menu_keyboard(), parse_mode="HTML")


# ==================== ПРОВЕРКА ПОДПИСКИ НА КАНАЛ ====================

@router.callback_query(F.data == "check_subscription")
async def cb_check_subscription(callback: types.CallbackQuery, session: AsyncSession):
    """Обработчик кнопки проверки подписки на канал"""
    from bot import _bot_instance
    
    if not _bot_instance:
        await callback.answer("⚠️ Ошибка: бот не инициализирован!", show_alert=True)
        return
    
    user = await get_or_create_user(session, callback.from_user.id)
    bot = _bot_instance
    
    # Если бонус уже выдан — просто показываем статус
    if user.channel_subscribed:
        await callback.answer("✅ Бонус уже активен! mining_bonus ×1.5", show_alert=True)
        return
    
    # Проверяем подписку
    is_subscribed = await check_channel_subscription(bot, user.id)
    
    if is_subscribed:
        # Выдаём бонус
        user.mining_bonus = 1.5
        user.channel_subscribed = True
        await session.commit()
        
        await callback.answer(
            "✅ Спасибо за подписку! Бонус ×1.5 активирован!",
            show_alert=True
        )
        
        # Отправляем уведомление с информацией о бонусе
        bonus_text = (
            f"🎉 <b>Вам засчитан вечный бонус к копанию руды ×1.5!</b>\n\n"
            f"Теперь ваша добыча увеличена на 50%.\n"
            f"Бонус действует постоянно и не требует повторной подписки."
        )
        await callback.message.answer(bonus_text, parse_mode="HTML")
    else:
        # Не подписан — предлагаем подписаться
        await callback.answer("⚠️ Вы не подписаны на канал!", show_alert=True)
        
        # Показываем кнопку с предложением подписаться
        subs_text = (
            f"⚠️ <b>Вы не подписаны на канал!</b>\n\n"
            f"Чтобы получить вечный бонус ×1.5 к добыче руды,\n"
            f"подпишитесь на наш канал:\n\n"
            f"<a href='https://t.me/evo_ban_news'>📢 @evo_ban_news</a>"
        )
        await callback.message.answer(
            subs_text,
            reply_markup=get_subscription_keyboard(),
            parse_mode="HTML"
        )
    
    await callback.answer()


# ==================== КОМАНДЫ ====================

@router.message(Command("bal"))
@router.message(lambda msg: msg.text and msg.text.lower() == "б")
async def cmd_balance(message: types.Message, session: AsyncSession):
    """Баланс"""
    user = await get_or_create_user(session, message.from_user.id)
    text = f"💰 <b>Баланс</b>\n\n💵 {format_number(user.balance)}\n🎆 {format_number(user.plasma)}\n📊 ур. {user.level}"
    await message.answer(text, parse_mode="HTML")
    

@router.message(Command("inv"))
@router.message(lambda msg: msg.text and msg.text.lower() == "инв")
async def cmd_inventory(message: types.Message, session: AsyncSession):
    """Инвентарь по команде /inv или 'инв'"""
    text, ore_count = await build_inventory_text(session, message.from_user.id, "ore")
    await message.answer(text, reply_markup=get_inventory_keyboard(ore_count), parse_mode="HTML")


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
    """Меню копания / обновление — проверяет подписку и читает состояние"""
    user = await get_or_create_user(session, callback.from_user.id)
    ms = await get_or_create_session(session, user.id)
    now = datetime.utcnow()
    
    # Проверяем подписку и выдаём бонус (если ещё не выдан)
    from bot import _bot_instance
    if _bot_instance and not user.channel_subscribed:
        is_subscribed = await check_channel_subscription(_bot_instance, user.id)
        if is_subscribed:
            user.mining_bonus = 1.5
            user.channel_subscribed = True
            await session.commit()
    
    if user.is_mining and ms.is_active and ms.end_time and now < ms.end_time:
        # Сессия идёт — читаем актуальное состояние из БД (фон уже обновляет)
        # Пересчитаем руду на всякий случай (мощность могла измениться)
        power = calculate_power(user.pickaxe_power, user.booster_power, user.mining_bonus or 1.0)
        ms.ores_dug = int(ms.hits * power) if ms.hits else 0
        await session.commit()
        
        # Показать актуальный статус
        text = await build_mining_active_text(session, user, ms, now)
        
        await callback.message.edit_text(text, reply_markup=get_mining_menu_keyboard(is_mining=True, mining_active=True), parse_mode="HTML")
        
    elif user.is_mining and ms.is_active:
        # Время вышло — читаем накопленные значения из БД (фон уже всё посчитал)
        # Пересчитаем руду на всякий случай
        power = calculate_power(user.pickaxe_power, user.booster_power, user.mining_bonus or 1.0)
        ms.ores_dug = int(ms.hits * power) if ms.hits else 0
        
        # Используем накопленные значения
        hits = ms.hits or 0
        ores = ms.ores_dug or 0
        plasma = ms.plasma_dug or 0
        cases_count = ms.cases_found or 0
        
        ms.is_active = False
        user.is_mining = False
        user.session_hits = hits
        user.session_ores = ores
        user.session_plasma = plasma
        user.session_cases = cases_count
        await session.commit()
        
        # Отправляем НОВОЕ сообщение с 🔔
        await mining_finished_by_time(callback.message, session, user, ms)
        
    else:
        # Копание не запущено — показываем начальное меню
        mine = MINES.get(user.current_mine, MINES[0])
        mine_name = mine["name"]
        ore_name = mine["ore"].capitalize()
        power = calculate_power(user.pickaxe_power, user.booster_power, user.mining_bonus or 1.0)
        
        power_text = f"×{power:.1f}"
        if user.mining_bonus and user.mining_bonus > 1.0:
            power_text += f" (включая бонус ×{user.mining_bonus:.1f})"
        
        text = (
            f"⛏ Ты копаешь\n"
            f"{'·' * 28}\n"
            f"⛰ Шахта : {mine_name}\n"
            f"🔥 Мощность : {power_text}\n"
            f"📦 Шанс найти кейс : ×{(user.case_chance or 3.0) / 3.0:.1f}\n"
            f"⏳ Времени прошло : 0с.\n"
            f"{'·' * 28}\n"
            f"⛏ Удары киркой : 0\n"
            f"🧱 Руды добыто : 0\n"
            f"🎆 Плазмы добыто : 0\n"
            f"{'·' * 28}\n"
            f"⏳ Осталось копать : {format_time(user.mining_duration or BASE_MINING_TIME)}\n\n"
            f"<i>Нажми 🔨 Добывать!</i>"
        )
        await callback.message.edit_text(text, reply_markup=get_mining_menu_keyboard(), parse_mode="HTML")
    
    await callback.answer()


async def build_mining_active_text(session: AsyncSession, user, ms: MiningSession, now: datetime) -> str:
    """Построить текст активной добычи"""
    mine = MINES.get(user.current_mine, MINES[0])
    mine_name = mine["name"]
    
    power = calculate_power(user.pickaxe_power, user.booster_power, user.mining_bonus or 1.0)
    case_chance = (user.case_chance or 3.0) / 3.0
    
    # Время прошло
    elapsed_seconds = int((now - ms.start_time).total_seconds()) if ms.start_time else 0
    
    # Время осталось
    remaining_seconds = 0
    if ms.end_time:
        remaining_seconds = int((ms.end_time - now).total_seconds())
        remaining_seconds = max(0, remaining_seconds)
    
    hits = ms.hits or 0
    ores = ms.ores_dug or 0
    plasma = ms.plasma_dug or 0
    cases_count = ms.cases_found or 0
    
    power_text = f"×{power:.1f}"
    if user.mining_bonus and user.mining_bonus > 1.0:
        power_text += f" (вкл. бонус ×{user.mining_bonus:.1f})"
    
    text = (
        f"⛏ Ты копаешь\n"
        f"{'·' * 28}\n"
        f"⛰ Шахта : {mine_name}\n"
        f"🔥 Мощность : {power_text}\n"
        f"📦 Шанс найти кейс : ×{case_chance:.1f}\n"
        f"⏳ Времени прошло : {elapsed_seconds}с.\n"
        f"{'·' * 28}\n"
        f"⛏ Удары киркой : {hits}\n"
        f"🧱 Руды добыто : {ores:,}\n"
        f"🎆 Плазмы добыто : {plasma}\n"
        f"{'·' * 28}\n"
        f"⏳ Осталось копать : {format_time(remaining_seconds)}"
    )
    
    return text


@router.callback_query(F.data == "start_mining")
async def cb_start_mining(callback: types.CallbackQuery, session: AsyncSession):
    """Начать добычу - сразу показываем активный статус и запускаем таймер"""
    user = await get_or_create_user(session, callback.from_user.id)
    
    if user.is_mining:
        await callback.answer("⚠️ Уже копаете!", show_alert=True)
        return
    
    now = datetime.utcnow()
    mining_duration = user.mining_duration or BASE_MINING_TIME
    end_time = now + timedelta(seconds=mining_duration)
    
    mine = MINES.get(user.current_mine, MINES[0])
    ore_name = mine["ore"]
    power = calculate_power(user.pickaxe_power, user.booster_power, user.mining_bonus or 1.0)
    
    # Устанавливаем состояние добычи
    user.is_mining = True
    user.mining_start = now
    user.mining_end = end_time
    user.last_update = now
    
    ms = await get_or_create_session(session, user.id)
    ms.mine_id = user.current_mine
    ms.mine_name = mine["name"]
    ms.ore_name = ore_name
    ms.power = power
    ms.start_time = now
    ms.end_time = end_time
    ms.hits = 1  # Сразу 1 удар (с первой секунды)
    ms.ores_dug = int(power)  # Сразу 1 руда × мощность
    ms.plasma_dug = 0
    ms.cases_found = 0
    ms.cases_list = json.dumps([])
    ms.is_active = True
    ms.last_update = now
    ms.chat_id = callback.message.chat.id
    ms.notification_sent = False
    
    await session.commit()
    
    # СРАЗУ считаем первый удар
    if random.random() * 100 < (user.plasma_chance or PLASMA_CHANCE):
        ms.plasma_dug = 1
    
    if random.random() * 100 < CASE_CHANCE:
        ms.cases_list = json.dumps([get_random_case()])
        ms.cases_found = 1
    
    await session.commit()
    
    # Сразу показываем активный статус (без обновления)
    text = await build_mining_active_text(session, user, ms, now)
    
    await callback.message.edit_text(
        text,
        reply_markup=get_mining_menu_keyboard(is_mining=True, mining_active=True),
        parse_mode="HTML"
    )
    await callback.answer("🎉 Поехали!")


@router.callback_query(F.data == "update_mining")
async def cb_update_mining(callback: types.CallbackQuery, session: AsyncSession):
    """Обновить статус добычи — только читает состояние из БД (фон уже обновляет)"""
    user = await get_or_create_user(session, callback.from_user.id)
    ms = await get_or_create_session(session, user.id)
    
    if not user.is_mining or not ms.is_active:
        await callback.answer("⚠️ Не копаете!", show_alert=True)
        return
    
    now = datetime.utcnow()
    if ms.end_time and now >= ms.end_time:
        # Время вышло — читаем накопленные значения
        power = calculate_power(user.pickaxe_power, user.booster_power, user.mining_bonus or 1.0)
        ms.ores_dug = int(ms.hits * power) if ms.hits else 0
        
        ms.is_active = False
        user.is_mining = False
        user.session_hits = ms.hits or 0
        user.session_ores = ms.ores_dug or 0
        user.session_plasma = ms.plasma_dug or 0
        user.session_cases = ms.cases_found or 0
        await session.commit()
        
        await callback.answer("⏰ Время вышло!")
        await mining_finished_by_time(callback.message, session, user, ms)
        return
    
    # Просто пересчитываем руду (мощность могла измениться)
    power = calculate_power(user.pickaxe_power, user.booster_power, user.mining_bonus or 1.0)
    ms.ores_dug = int(ms.hits * power) if ms.hits else 0
    ms.last_update = now
    await session.commit()
    
    # Показываем актуальное состояние
    text = await build_mining_active_text(session, user, ms, now)
    await callback.message.edit_text(text, reply_markup=get_mining_menu_keyboard(is_mining=True, mining_active=True), parse_mode="HTML")
    await callback.answer("🔄")


@router.callback_query(F.data == "stop_mining")
async def cb_stop_mining(callback: types.CallbackQuery, session: AsyncSession):
    """Остановить добычу (само-остановка через кнопку 🚫) — читает состояние из БД"""
    user = await get_or_create_user(session, callback.from_user.id)
    ms = await get_or_create_session(session, user.id)
    
    if not user.is_mining or not ms.is_active:
        await callback.answer("⚠️ Не копаете!", show_alert=True)
        return
    
    now = datetime.utcnow()
    
    # Пересчитать руду (мощность могла измениться)
    power = calculate_power(user.pickaxe_power, user.booster_power, user.mining_bonus or 1.0)
    ms.ores_dug = int(ms.hits * power) if ms.hits else 0
    
    ms.is_active = False
    ms.end_time = now
    user.is_mining = False
    
    # Используем накопленные значения (фон уже всё посчитал)
    hits = ms.hits or 0
    ores = ms.ores_dug or 0
    plasma = ms.plasma_dug or 0
    cases_count = ms.cases_found or 0
    
    user.session_hits = hits
    user.session_ores = ores
    user.session_plasma = plasma
    user.session_cases = cases_count
    
    await session.commit()
    await callback.answer("⏹️ Остановлено")
    
    mine = MINES.get(user.current_mine, MINES[0])
    ore_name = mine["ore"].capitalize()
    
    # Форматируем время
    mins = hits // 60
    secs = hits % 60
    time_str = f"{mins}м. {secs}с."
    
    text = (
        f"🎒 <b>Ресурсы собраны!</b>\n"
        f"{'·' * 28}\n"
        f"⛰ Шахта : {ms.mine_name or mine['name']}\n"
        f"⏳ Время копания : {time_str}\n"
        f"{'·' * 28}\n"
        f"⛏ Удары киркой : {hits}\n"
        f"🧱 Руды добыто : {ores:,}\n"
        f"🎆 Плазмы добыто : {plasma}\n"
        f"{'·' * 28}\n"
        f"<i>Ты можешь продать руду,</i>\n"
        f"<i>открыв 🎒 Рюкзак</i>"
    )
    
    await callback.message.edit_text(text, reply_markup=get_collect_completed_keyboard(ms.mine_name or mine["name"], hits, ores, plasma), parse_mode="HTML")


@router.callback_query(F.data == "collect_from_notification")
async def cb_collect_from_notification(callback: types.CallbackQuery, session: AsyncSession):
    """Собрать из уведомления (когда время закончилось) - показывает итоги сбора"""
    user = await get_or_create_user(session, callback.from_user.id)
    ms = await get_or_create_session(session, user.id)
    
    # Используем накопленные значения из сессии майнинга
    hits = ms.hits or 0
    ores = ms.ores_dug or 0
    plasma = ms.plasma_dug or 0
    
    mine = MINES.get(user.current_mine, MINES[0])
    mine_name = ms.mine_name or mine["name"]
    
    # Форматируем время
    mins = hits // 60
    secs = hits % 60
    time_str = f"{mins}м. {secs}с."
    
    text = (
        f"🎒 <b>Ресурсы собраны!</b>\n"
        f"{'·' * 28}\n"
        f"⛰ Шахта : {mine_name}\n"
        f"⏳ Время копания : {time_str}\n"
        f"{'·' * 28}\n"
        f"⛏ Удары киркой : {hits}\n"
        f"🧱 Руды получено : {ores:,}\n"
        f"🎆 Плазмы получено : {plasma}\n"
        f"{'·' * 28}\n"
        f"<i>Ты можешь продать руду,</i>\n"
        f"<i>открыв 🎒 Рюкзак</i>"
    )
    
    await callback.message.edit_text(text, reply_markup=get_collect_completed_keyboard(mine_name, hits, ores, plasma), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "collect_resources")
async def cb_collect_resources(callback: types.CallbackQuery, session: AsyncSession):
    """Собрать ресурсы из сообщения о завершении"""
    user = await get_or_create_user(session, callback.from_user.id)
    ms = await get_or_create_session(session, user.id)
    
    if user.session_ores <= 0:
        await callback.answer("⚠️ Пусто!", show_alert=True)
        return
    
    ore_name = ms.ore_name or MINES.get(user.current_mine, MINES[0])["ore"]
    ores_collected = user.session_ores
    plasma_collected = user.session_plasma
    cases_list = json.loads(ms.cases_list) if ms.cases_list else []
    
    # Добавляем руду в инвентарь
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
    
    # Сброс сессии
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
    
    # Форматируем время
    hits = user.session_hits if user.session_hits else (ms.hits if ms.hits else 0)
    mins = hits // 60
    secs = hits % 60
    time_str = f"{mins}м. {secs}с."
    
    mine_name = ms.mine_name or MINES.get(user.current_mine, MINES[0])["name"]
    
    text = (
        f"🎒 <b>Ресурсы собраны!</b>\n"
        f"{'·' * 28}\n"
        f"⛰ Шахта : {mine_name}\n"
        f"⏳ Время копания : {time_str}\n"
        f"{'·' * 28}\n"
        f"⛏ Удары киркой : {hits}\n"
        f"🧱 Руды получено : {ores_collected:,}\n"
        f"🎆 Плазмы получено : {plasma_collected}\n"
        f"{'·' * 28}\n"
        f"<i>Ты можешь продать руду,</i>\n"
        f"<i>открыв 🎒 Рюкзак</i>"
    )
    
    await callback.message.edit_text(text, reply_markup=get_collect_completed_keyboard(mine_name, hits, ores_collected, plasma_collected), parse_mode="HTML")
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

async def build_inventory_text(session: AsyncSession, user_id: int, tab: str = "ore") -> tuple[str, int]:
    """Построить текст инвентаря для указанной вкладки"""
    result = await session.execute(
        select(Inventory).where(Inventory.user_id == user_id).order_by(Inventory.item_name)
    )
    items = result.scalars().all()
    
    if tab == "ore":
        text = "🧱 <b>Руда</b>\n"
        text += f"{'·' * 28}\n"
        ore_count = 0
        has_items = False
        
        for item in items:
            if item.item_type == "ore" and item.quantity > 0:
                has_items = True
                ore_count += item.quantity
                text += f"{item.item_name.capitalize()} : {item.quantity:.1f} ед\n"
                text += f"{'·' * 28}\n"
        
        if not has_items:
            text = "🧱 <b>Руда</b>\n"
            text += f"{'·' * 28}\n"
            text += "Здесь пока ничего нет\n"
        
        # Добавляем информацию о канале
        text += f"\n🤩 <i>Хочешь вечный множитель руды ×1.5?</i>\n"
        text += f"<a href='https://t.me/evo_ban_news'>Подпишись на канал бота и получи его!</a>"
        
        return text, ore_count
    
    elif tab == "materials":
        text = "🎨 <b>Материалы</b>\n"
        text += f"{'·' * 28}\n"
        
        has_items = False
        for item in items:
            if item.item_type == "material" and item.quantity > 0:
                has_items = True
                text += f"{item.item_name.capitalize()} : {item.quantity} ед\n"
        
        if not has_items:
            text += "Здесь пока ничего нет\n"
        
        return text, 0
    
    elif tab == "consumables":
        text = "🧪 <b>Расходники</b>\n"
        text += f"{'·' * 28}\n"
        
        has_items = False
        for item in items:
            if item.item_type == "consumable" and item.quantity > 0:
                has_items = True
                text += f"{item.item_name.capitalize()} : {item.quantity} ед\n"
        
        if not has_items:
            text += "Здесь пока ничего нет\n"
        
        return text, 0
    
    return "🎒 <b>Инвентарь</b>\n\n📭 Пусто", 0


@router.callback_query(F.data == "inventory")
async def cb_inventory(callback: types.CallbackQuery, session: AsyncSession):
    """Инвентарь - вкладка Руда по умолчанию"""
    text, ore_count = await build_inventory_text(session, callback.from_user.id, "ore")
    await callback.message.edit_text(text, reply_markup=get_inventory_keyboard(ore_count), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "inv_tab_ore")
async def cb_inv_tab_ore(callback: types.CallbackQuery, session: AsyncSession):
    """Вкладка Руда"""
    text, ore_count = await build_inventory_text(session, callback.from_user.id, "ore")
    await callback.message.edit_text(text, reply_markup=get_inventory_keyboard(ore_count), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "inv_tab_materials")
async def cb_inv_tab_materials(callback: types.CallbackQuery, session: AsyncSession):
    """Вкладка Материалы"""
    text, _ = await build_inventory_text(session, callback.from_user.id, "materials")
    await callback.message.edit_text(text, reply_markup=get_inventory_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "inv_tab_consumables")
async def cb_inv_tab_consumables(callback: types.CallbackQuery, session: AsyncSession):
    """Вкладка Расходники"""
    text, _ = await build_inventory_text(session, callback.from_user.id, "consumables")
    await callback.message.edit_text(text, reply_markup=get_inventory_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "sell_all_ores")
async def cb_sell_all(callback: types.CallbackQuery, session: AsyncSession):
    """Продать всю руду"""
    user = await get_or_create_user(session, callback.from_user.id)
    result = await session.execute(select(Inventory).where(Inventory.user_id == user.id, Inventory.item_type == "ore"))
    ores = result.scalars().all()
    
    total = 0
    count = 0
    sold_items = []
    
    for ore in ores:
        if ore.quantity > 0:
            price = ORE_PRICES.get(ore.item_name, 0)
            item_total = ore.quantity * price
            total += item_total
            count += ore.quantity
            sold_items.append(f"{ore.item_name.capitalize()}: {ore.quantity} × {price} = {item_total}")
            ore.quantity = 0
    
    if total == 0:
        await callback.answer("⚠️ Нет руды!", show_alert=True)
        return
    
    user.balance += total
    await session.commit()
    
    # Текст о продаже
    text = f"💸 <b>Продано!</b>\n\n"
    text += f"🧱 Всего руды: {format_number(count)}\n"
    text += f"💰 Получено: {format_number(total)}\n"
    text += f"💳 Баланс: {format_number(user.balance)}"
    
    await callback.message.edit_text(text, reply_markup=get_inventory_keyboard(), parse_mode="HTML")
    await callback.answer(f"💰 +{format_number(total)}")


# ==================== НАВИГАЦИЯ ====================

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: types.CallbackQuery, session: AsyncSession):
    """Главное меню"""
    user = await get_or_create_user(session, callback.from_user.id)
    text = f"👋 {user.first_name}\n\n💰 {format_number(user.balance)}\n🎆 {format_number(user.plasma)}\n📊 ур. {user.level}"
    await callback.message.edit_text(text, reply_markup=get_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "close_menu")
async def cb_close_menu(callback: types.CallbackQuery):
    """Закрыть"""
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data == "toggle_notifications")
async def cb_toggle_notifications(callback: types.CallbackQuery, session: AsyncSession):
    """Переключить уведомления о завершении копания"""
    new_state = await toggle_notifications(session, callback.from_user.id)
    
    if new_state:
        await callback.answer("🔔 Уведомления включены!")
    else:
        await callback.answer("🔕 Уведомления отключены!")
    
    # Обновляем клавиатуру с новым состоянием
    from keyboards import get_mining_finished_keyboard
    await callback.message.edit_reply_markup(reply_markup=get_mining_finished_keyboard(new_state))


@router.callback_query(F.data == "shop")
async def cb_shop(callback: types.CallbackQuery, session: AsyncSession):
    """Магазин"""
    user = await get_or_create_user(session, callback.from_user.id)
    pick_cost = int(100 * (1.5 ** user.pickaxe_power))
    boost_cost = int(200 * (2.0 ** user.booster_power))
    
    text = (
        f"🏪 <b>Магазин</b>\n\n"
        f"💰 {format_number(user.balance)} | 🎆 {format_number(user.plasma)}\n\n"
        f"⚒️ Кирка +0.5: {format_number(pick_cost)}💰 (сейчас ×{user.pickaxe_power:.2f})\n"
        f"🚀 Бустер +1.0: {format_number(boost_cost)}💰 (сейчас ×{user.booster_power:.2f})"
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
    Форматирование больших чисел с буквенными суффиксами:
    K - тысячи (10^3)
    M - миллионы (10^6)
    B - миллиарды (10^9)
    T - триллионы (10^12)
    Qa - квадриллионы (10^15)
    Qi - квинтиллионы (10^18)
    Sx - секстиллионы (10^21)
    Sp - септиллионы (10^24)
    O - октиллионы (10^27)
    N - нониллионы (10^30)
    D - дециллионы (10^33)
    Далее: Aa, Bb, Cc, Dd... до Zzz
    """
    if num < 1000:
        return str(int(num)) if isinstance(num, int) or num == int(num) else f"{num:.2f}"
    
    # Для очень больших чисел (>= 10^36) используем генерацию суффиксов Aa, Bb, Cc...
    if num >= 10**36:
        # Находим правильный exponent (степень 10, кратную 3)
        # exponent = 36 -> index = 0 -> Aa
        # exponent = 39 -> index = 1 -> Bb
        # exponent = 42 -> index = 2 -> Cc
        # и т.д.
        exponent = 36
        while num >= (10 ** (exponent + 3)):
            exponent += 3
        
        # Вычисляем индекс для генерации суффикса
        index = (exponent - 36) // 3
        
        if index < 26:
            # Aa-Zz (одинарные буквы)
            first_char = chr(ord('A') + index)
            second_char = first_char.lower()
            suffix = f"{first_char}{second_char}"
        elif index < 26 * 26:
            # Aaa-Zzz (двойные буквы)
            first_idx = index // 26
            second_idx = index % 26
            first_char = chr(ord('A') + first_idx)
            second_char = chr(ord('a') + second_idx)
            third_char = second_char
            suffix = f"{first_char}{second_char}{third_char}"
        else:
            # Для экстремально больших чисел
            suffix = "inf"
        
        divisor = 10 ** exponent
        value = num / divisor
        
        if value >= 100:
            return f"{int(value)}{suffix}"
        elif value >= 10:
            return f"{value:.1f}{suffix}"
        else:
            return f"{value:.2f}{suffix}"
    
    # Основные суффиксы для чисел < 10^36
    suffixes = [
        (10**33, "D"),    # Дециллионы
        (10**30, "N"),    # Нониллионы
        (10**27, "O"),    # Октиллионы
        (10**24, "Sp"),   # Септиллионы
        (10**21, "Sx"),   # Секстиллионы
        (10**18, "Qi"),   # Квинтиллионы
        (10**15, "Qa"),   # Квадриллионы
        (10**12, "T"),    # Триллионы
        (10**9, "B"),     # Миллиарды
        (10**6, "M"),     # Миллионы
        (10**3, "K"),     # Тысячи
    ]
    
    # Проверяем основные суффиксы
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
        f"💳 *Баланс : {format_number(user.balance)} Эво-Коинов*\n"
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
