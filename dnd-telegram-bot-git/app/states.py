from aiogram.fsm.state import State, StatesGroup


class LoginState(StatesGroup):
    login = State()
    password = State()


class CreateCharacterState(StatesGroup):
    login = State()
    password = State()
    display_name = State()


class CreateItemState(StatesGroup):
    name = State()
    description = State()
    price = State()
    rarity = State()
    photo = State()


class AdminNumberState(StatesGroup):
    amount = State()


class GiveItemState(StatesGroup):
    quantity = State()
