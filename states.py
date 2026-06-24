"""Машины состояний для FSM"""
from aiogram.fsm.state import State, StatesGroup


class MiningState(StatesGroup):
    """Состояния для добычи"""
    selecting_mine = State()
    mining_active = State()
    collecting = State()


class TransferState(StatesGroup):
    """Состояния для перевода"""
    entering_username = State()
    entering_amount = State()
    confirming = State()


class ShopState(StatesGroup):
    """Состояния для магазина"""
    selecting_upgrade = State()
    confirming_purchase = State()
