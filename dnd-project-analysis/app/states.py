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
    category = State()
    price = State()
    rarity = State()
    weight = State()
    consumable = State()
    heal_hp = State()
    equipment = State()
    loot_chance = State()
    availability = State()
    shop_quantity = State()
    photo = State()


class EditItemState(StatesGroup):
    value = State()
    photo = State()


class CreateCategoryState(StatesGroup):
    name = State()


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


class CreateSessionState(StatesGroup):
    title = State()
    description = State()


class SessionNotifyState(StatesGroup):
    date_text = State()
    message = State()


class RestState(StatesGroup):
    short_hp = State()
    note = State()


class EditCharacterState(StatesGroup):
    value = State()


class CharacterNotesState(StatesGroup):
    notes = State()


class SessionCardState(StatesGroup):
    value = State()


class ItemSearchState(StatesGroup):
    query = State()


class CampaignClueState(StatesGroup):
    title = State()
    details = State()
