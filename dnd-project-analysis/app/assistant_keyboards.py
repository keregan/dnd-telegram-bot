from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.item_rules import EQUIPMENT_SLOTS


def search_source_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Магазин', callback_data='assistant:search_source:shop')
    builder.button(text='Мой инвентарь', callback_data='assistant:search_source:inventory')
    builder.button(text='Назад', callback_data='menu:main')
    builder.adjust(2, 1)
    return builder.as_markup()


def search_filter_keyboard(source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Все', callback_data=f'assistant:search_filter:{source}:all')
    builder.button(text='Расходники', callback_data=f'assistant:search_filter:{source}:consumable')
    builder.button(text='Экипировка', callback_data=f'assistant:search_filter:{source}:equipment')
    if source == 'shop':
        builder.button(text='По карману', callback_data=f'assistant:search_filter:{source}:affordable')
    builder.button(text='Назад', callback_data='assistant:search')
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def search_results_keyboard(items: list[dict], source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    action = 'assistant:search_shop_item' if source == 'shop' else 'assistant:search_inventory_item'
    for item in items:
        quantity = f' x{item["quantity"]}' if source == 'inventory' else ''
        builder.button(text=f'{item["name"]}{quantity}', callback_data=f'{action}:{item["id"]}')
    builder.button(text='Новый поиск', callback_data='assistant:search')
    builder.button(text='Главное меню', callback_data='menu:main')
    builder.adjust(1)
    return builder.as_markup()


def consumable_confirm_keyboard(item_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Да, использовать x1', callback_data=f'inventory:use:{item_id}')
    builder.button(text='Нет, оставить', callback_data=f'inventory:item:{item_id}')
    builder.adjust(1)
    return builder.as_markup()


def create_consumable_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Да, расходуется', callback_data='create_item:consumable:yes')
    builder.button(text='Нет', callback_data='create_item:consumable:no')
    builder.adjust(2)
    return builder.as_markup()


def create_equipment_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Не экипируется', callback_data='create_item:equipment:none')
    for value, title in EQUIPMENT_SLOTS:
        builder.button(text=title, callback_data=f'create_item:equipment:{value}')
    builder.adjust(1)
    return builder.as_markup()


def condition_duration_keyboard(character_id: int, condition: str) -> InlineKeyboardMarkup:
    prefix = f'assistant:condition_duration:{character_id}:{condition}'
    builder = InlineKeyboardBuilder()
    builder.button(text='1 ход', callback_data=f'{prefix}:turns:1')
    builder.button(text='3 хода', callback_data=f'{prefix}:turns:3')
    builder.button(text='1 раунд', callback_data=f'{prefix}:rounds:1')
    builder.button(text='3 раунда', callback_data=f'{prefix}:rounds:3')
    builder.button(text='До отдыха', callback_data=f'{prefix}:rest:0')
    builder.button(text='Снять вручную', callback_data=f'{prefix}:manual:0')
    builder.adjust(2, 2, 2)
    return builder.as_markup()


def clues_admin_keyboard(session_id: int, clues: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Добавить зацепку', callback_data=f'assistant:clue_add:{session_id}')
    for clue in clues:
        builder.button(text=f'Удалить: {clue["title"][:30]}', callback_data=f'assistant:clue_delete:{session_id}:{clue["id"]}')
    builder.button(text='К сессии', callback_data=f'admin:session:{session_id}')
    builder.adjust(1)
    return builder.as_markup()


def group_loot_admin_keyboard(session_id: int, loot: dict | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Создать новый набор x3', callback_data=f'assistant:loot_generate:{session_id}')
    if loot:
        for item in loot.get('items', []):
            if item.get('assigned_character_id') is None:
                builder.button(text=f'Распределить: {item["name"][:28]}', callback_data=f'assistant:loot_choose:{session_id}:{item["id"]}')
    builder.button(text='К сессии', callback_data=f'admin:session:{session_id}')
    builder.adjust(1)
    return builder.as_markup()


def group_loot_characters_keyboard(session_id: int, loot_item_id: int, characters: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for character in characters:
        builder.button(text=character['display_name'], callback_data=f'assistant:loot_assign:{session_id}:{loot_item_id}:{character["id"]}')
    builder.button(text='Назад', callback_data=f'assistant:loot_admin:{session_id}')
    builder.adjust(1)
    return builder.as_markup()


def death_saves_keyboard(character_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Успех', callback_data=f'assistant:death_update:{character_id}:success')
    builder.button(text='Провал', callback_data=f'assistant:death_update:{character_id}:failure')
    builder.button(text='Сбросить', callback_data=f'assistant:death_update:{character_id}:reset')
    builder.button(text='К персонажу', callback_data=f'admin:character:{character_id}')
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def operations_keyboard(rows: list[dict]) -> InlineKeyboardMarkup:
    reversible = {'xp', 'gold', 'quick_reward_xp', 'quick_reward_gold', 'item', 'random_loot', 'group_loot'}
    builder = InlineKeyboardBuilder()
    for row in rows:
        if row.get('reverted_at') or row.get('type') not in reversible or int(row.get('amount') or 0) <= 0:
            continue
        builder.button(text=f'Отменить #{row["id"]}', callback_data=f'assistant:undo_ask:{row["id"]}')
    builder.button(text='Назад', callback_data='admin:system_menu')
    builder.adjust(1)
    return builder.as_markup()


def undo_confirm_keyboard(transaction_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Да, отменить', callback_data=f'assistant:undo_confirm:{transaction_id}')
    builder.button(text='Нет', callback_data='assistant:operations')
    builder.adjust(1)
    return builder.as_markup()
