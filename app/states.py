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
    loot_chance = State()
    availability = State()
    shop_quantity = State()
    photo = State()


class AdminNumberState(StatesGroup):
    amount = State()


class GiveItemState(StatesGroup):
    quantity = State()


class SetItemStockState(StatesGroup):
    quantity = State()



class TransferGoldState(StatesGroup):
    amount = State()


class TransferItemState(StatesGroup):
    quantity = State()


class SetItemLootChanceState(StatesGroup):
    chance = State()


class CreateQuestState(StatesGroup):
    title = State()
    description = State()
    xp_reward = State()
    gold_reward = State()
    item_select = State()
    item_quantity = State()
