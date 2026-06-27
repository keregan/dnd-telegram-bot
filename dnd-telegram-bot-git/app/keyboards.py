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


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='👤 Профиль', callback_data='player:profile')
    builder.button(text='🎒 Инвентарь', callback_data='player:inventory')
    builder.button(text='🛒 Магазин', callback_data='shop:list')
    builder.button(text='🔐 Войти', callback_data='auth:login')
    if is_admin:
        builder.button(text='⚙️ Админ-панель', callback_data='admin:menu')
    builder.adjust(2, 2, 1)
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
            text=f'{character["display_name"]} | XP {character["xp"]} | 🪙 {character["gold"]}',
            callback_data=f'{action}:{character["id"]}',
        )
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def items_keyboard(items: list[dict], action: str, back_callback: str = 'menu:main') -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        active_mark = '' if item.get('is_active', 1) else '🚫 '
        builder.button(
            text=f'{active_mark}{item["name"]} — {item["price"]} 🪙',
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


def rarity_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for title, value in RARITIES:
        builder.button(text=title, callback_data=f'rarity:{value}')
    builder.adjust(1)
    return builder.as_markup()
