from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


RARITIES = [
    ('Обычный', 'common'),
    ('Необычный', 'uncommon'),
    ('Редкий', 'rare'),
    ('Эпический', 'epic'),
    ('Легендарный', 'legendary'),
]


def stock_label(item: dict) -> str:
    quantity = int(item.get('shop_quantity', -1))
    if not item.get('is_active', 1):
        return 'только выдача'
    if quantity < 0:
        return '∞'
    if quantity == 0:
        return 'нет в наличии'
    return f'{quantity} шт.'


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='👤 Профиль', callback_data='player:profile')
    builder.button(text='🎒 Инвентарь', callback_data='player:inventory')
    builder.button(text='🛒 Магазин', callback_data='shop:list')
    builder.button(text='📈 Уровни', callback_data='player:levels')
    builder.button(text='🔁 Передать', callback_data='transfer:menu')
    builder.button(text='🔐 Войти', callback_data='auth:login')
    if is_admin:
        builder.button(text='⚙️ Админ-панель', callback_data='admin:menu')
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def admin_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='🧙 Создать персонажа', callback_data='admin:create_character')
    builder.button(text='👥 Персонажи', callback_data='admin:characters')
    builder.button(text='➕ Добавить XP', callback_data='admin:add_xp')
    builder.button(text='💰 Добавить монеты', callback_data='admin:add_gold')
    builder.button(text='🎁 Выдать предмет', callback_data='admin:give_item')
    builder.button(text='🛠️ Создать предмет', callback_data='admin:create_item')
    builder.button(text='📦 Все предметы', callback_data='admin:items')
    builder.button(text='📜 Квесты', callback_data='admin:quests')
    builder.button(text='🎲 Рандомный лут', callback_data='admin:random_loot')
    builder.button(text='⬅️ Главное меню', callback_data='menu:main')
    builder.adjust(1)
    return builder.as_markup()


def back_to_admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text='⬅️ Админ-панель', callback_data='admin:menu')]]
    )


def back_to_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text='⬅️ Главное меню', callback_data='menu:main')]]
    )


def characters_keyboard(characters: list[dict], action: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for character in characters:
        builder.button(
            text=f'{character["display_name"]} | ур. {character.get("level", 1)} | XP {character["xp"]} | 🪙 {character["gold"]}',
            callback_data=f'{action}:{character["id"]}',
        )
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def items_keyboard(items: list[dict], action: str, back_callback: str = 'menu:main') -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        active_mark = '' if item.get('is_active', 1) else '🚫 '
        quantity_text = f' ×{item["quantity"]}' if 'quantity' in item else ''
        stock_text = f' | {stock_label(item)}' if 'shop_quantity' in item else ''
        builder.button(
            text=f'{active_mark}{item["name"]}{quantity_text} — {item["price"]} 🪙{stock_text}',
            callback_data=f'{action}:{item["id"]}',
        )
    builder.button(text='⬅️ Назад', callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()


def item_details_keyboard(item_id: int, can_buy: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if can_buy:
        builder.button(text='Купить ×1', callback_data=f'shop:buy:{item_id}:1')
    builder.button(text='⬅️ Магазин', callback_data='shop:list')
    builder.button(text='🏠 Главное меню', callback_data='menu:main')
    builder.adjust(1)
    return builder.as_markup()


def inventory_item_keyboard(item_id: int, can_sell: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if can_sell:
        builder.button(text='Продать ×1', callback_data=f'inventory:sell:{item_id}:1')
    builder.button(text='Передать игроку', callback_data=f'inventory:transfer_start:{item_id}')
    builder.button(text='⬅️ Инвентарь', callback_data='player:inventory')
    builder.button(text='🏠 Главное меню', callback_data='menu:main')
    builder.adjust(1)
    return builder.as_markup()


def admin_item_manage_keyboard(item: dict) -> InlineKeyboardMarkup:
    item_id = int(item['id'])
    builder = InlineKeyboardBuilder()
    if item.get('is_active', 1):
        builder.button(text='🚫 Скрыть из магазина', callback_data=f'admin:toggle_item:{item_id}')
    else:
        builder.button(text='✅ Добавить в магазин', callback_data=f'admin:toggle_item:{item_id}')
    builder.button(text='🔢 Изменить остаток', callback_data=f'admin:set_stock:{item_id}')
    builder.button(text='🎲 Изменить шанс лута', callback_data=f'admin:set_loot_chance:{item_id}')
    builder.button(text='📦 Все предметы', callback_data='admin:items')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def rarity_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for title, value in RARITIES:
        builder.button(text=title, callback_data=f'rarity:{value}')
    builder.adjust(1)
    return builder.as_markup()


def item_availability_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='🛒 Добавить в магазин', callback_data='item_availability:shop')
    builder.button(text='🎁 Только выдача игрокам', callback_data='item_availability:private')
    builder.adjust(1)
    return builder.as_markup()



def transfer_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='💰 Передать монеты', callback_data='transfer:gold')
    builder.button(text='🎒 Передать предмет', callback_data='transfer:item')
    builder.button(text='⬅️ Главное меню', callback_data='menu:main')
    builder.adjust(1)
    return builder.as_markup()


def characters_select_keyboard(characters: list[dict], action: str, back_callback: str = 'menu:main') -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for character in characters:
        builder.button(
            text=f'{character["display_name"]} | ур. {character.get("level", 1)} | 🪙 {character["gold"]}',
            callback_data=f'{action}:{character["id"]}',
        )
    builder.button(text='⬅️ Назад', callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()


def quests_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='➕ Создать квест', callback_data='admin:create_quest')
    builder.button(text='📜 Список квестов', callback_data='admin:quest_list')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def quests_keyboard(quests: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for quest in quests:
        marker = '✅' if quest.get('is_active', 1) else '🚫'
        builder.button(text=f'{marker} {quest["title"]}', callback_data=f'admin:quest:{quest["id"]}')
    builder.button(text='➕ Создать квест', callback_data='admin:create_quest')
    builder.button(text='⬅️ Квесты', callback_data='admin:quests')
    builder.adjust(1)
    return builder.as_markup()


def quest_item_reward_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Без предмета', callback_data='quest_item:none')
    for item in items:
        builder.button(text=f'{item["name"]} — {item["price"]} 🪙', callback_data=f'quest_item:{item["id"]}')
    builder.adjust(1)
    return builder.as_markup()


def quest_details_keyboard(quest: dict) -> InlineKeyboardMarkup:
    quest_id = int(quest['id'])
    builder = InlineKeyboardBuilder()
    builder.button(text='🎁 Выдать награду', callback_data=f'admin:quest_award:{quest_id}')
    if quest.get('is_active', 1):
        builder.button(text='🚫 Скрыть квест', callback_data=f'admin:quest_toggle:{quest_id}')
    else:
        builder.button(text='✅ Вернуть квест', callback_data=f'admin:quest_toggle:{quest_id}')
    builder.button(text='📜 Список квестов', callback_data='admin:quest_list')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def quest_award_characters_keyboard(characters: list[dict], selected_ids: set[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for character in characters:
        mark = '✅' if int(character['id']) in selected_ids else '⬜'
        builder.button(text=f'{mark} {character["display_name"]}', callback_data=f'admin:quest_select:{character["id"]}')
    builder.button(text='🎁 Выдать выбранным', callback_data='admin:quest_award_confirm')
    builder.button(text='⬅️ Квесты', callback_data='admin:quest_list')
    builder.adjust(1)
    return builder.as_markup()


def random_loot_confirm_keyboard(character_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='🎲 Кинуть рандомный лут', callback_data=f'admin:random_loot_roll:{character_id}')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()
