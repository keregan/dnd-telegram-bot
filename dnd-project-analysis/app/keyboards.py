from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.gameplay import CHARACTER_CONDITIONS
from app.character_sheet import SECTION_LABELS
from app.item_rules import EQUIPMENT_SLOTS, equipment_slot_label


RARITIES = [
    ('Обычный', 'common'),
    ('Необычный', 'uncommon'),
    ('Редкий', 'rare'),
    ('Эпический', 'epic'),
    ('Легендарный', 'legendary'),
]

CATEGORIES = [
    ('⚔️ Оружие', 'weapon'),
    ('🛡️ Броня', 'armor'),
    ('🍖 Еда', 'food'),
    ('🍺 Питьё', 'drink'),
    ('✨ Магия', 'magic'),
    ('🧰 Инструменты', 'tools'),
    ('🧪 Расходники', 'consumable'),
    ('🎒 Снаряжение', 'gear'),
    ('📿 Аксессуары', 'accessory'),
    ('📦 Другое', 'other'),
]

CATEGORY_TITLES = {value: title for title, value in CATEGORIES}
CATEGORY_ORDER = {value: index for index, (_, value) in enumerate(CATEGORIES)}
PAGE_SIZE = 10
QUICK_REWARD_PRESETS = {
    'small': {'title': 'Малый бой', 'xp': 100, 'gold': 25},
    'medium': {'title': 'Средний бой', 'xp': 300, 'gold': 75},
    'boss': {'title': 'Босс', 'xp': 800, 'gold': 200},
}


def category_label(category: str | None) -> str:
    if not category:
        return CATEGORY_TITLES['other']
    return CATEGORY_TITLES.get(str(category), str(category))


def stock_label(item: dict) -> str:
    quantity = int(item.get('shop_quantity', -1))
    if not item.get('is_active', 1):
        return 'только выдача'
    if quantity < 0:
        return '∞'
    if quantity == 0:
        return 'нет в наличии'
    return f'{quantity} шт.'


def main_menu(is_admin: bool = False, is_logged_in: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='👤 Профиль', callback_data='player:profile')
    builder.button(text='🎒 Инвентарь', callback_data='player:inventory')
    builder.button(text='🛒 Магазин', callback_data='shop:list')
    builder.button(text='📖 Журнал', callback_data='player:journal')
    builder.button(text='🔎 Найти предмет', callback_data='assistant:search')
    builder.button(text='🔁 Передать', callback_data='transfer:menu')
    if is_logged_in:
        builder.button(text='🚪 Выйти из аккаунта', callback_data='auth:logout')
    else:
        builder.button(text='🔐 Войти', callback_data='auth:login')
    if is_admin:
        builder.button(text='⚙️ Админ-панель', callback_data='admin:menu')
    builder.adjust(2, 2, 1, 1, 1)
    return builder.as_markup()


def admin_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='👥 Персонажи', callback_data='admin:characters_menu')
    builder.button(text='🎲 Сессии', callback_data='admin:sessions')
    builder.button(text='⚡ Награда всей сессии', callback_data='admin:quick_rewards')
    builder.button(text='📦 Предметы и магазин', callback_data='admin:items_menu')
    builder.button(text='🛠️ Служебное', callback_data='admin:system_menu')
    builder.button(text='⬅️ Главное меню', callback_data='menu:main')
    builder.adjust(1)
    return builder.as_markup()


def admin_characters_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='🧙 Создать персонажа', callback_data='admin:create_character')
    builder.button(text='👥 Все персонажи', callback_data='admin:characters')
    builder.button(text='➕ Добавить XP', callback_data='admin:add_xp')
    builder.button(text='💰 Добавить монеты', callback_data='admin:add_gold')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def admin_sessions_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='🎲 Сессии', callback_data='admin:sessions')
    builder.button(text='🔔 Уведомления сессии', callback_data='admin:session_notifications')
    builder.button(text='🛌 Отдых', callback_data='admin:rests')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def admin_rewards_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='📜 Квесты', callback_data='admin:quests')
    builder.button(text='⚡ Быстрые награды', callback_data='admin:quick_rewards')
    builder.button(text='🎲 Рандомный лут', callback_data='admin:random_loot')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def admin_items_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='🎁 Выдать предмет', callback_data='admin:give_item')
    builder.button(text='🛠️ Создать предмет', callback_data='admin:create_item')
    builder.button(text='📂 Категории', callback_data='admin:categories')
    builder.button(text='📦 Все предметы', callback_data='admin:items')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def admin_system_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='🩺 Проверить базу', callback_data='admin:system_health')
    builder.button(text='🧭 Распределить предметы', callback_data='admin:auto_categorize_items')
    builder.button(text='↩️ Последние операции', callback_data='assistant:operations')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
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


def player_profile_keyboard(character: dict, has_active_initiative: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='📚 Лист персонажа', callback_data='player:sheet')
    builder.button(text='📈 Таблица уровней', callback_data='player:levels')
    builder.button(text='⬅️ Главное меню', callback_data='menu:main')
    builder.adjust(1)
    return builder.as_markup()


def session_card_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='✅ Буду', callback_data='assistant:rsvp:yes')
    builder.button(text='❔ Не уверен', callback_data='assistant:rsvp:maybe')
    builder.button(text='❌ Не смогу', callback_data='assistant:rsvp:no')
    builder.button(text='🧭 Перед игрой', callback_data='assistant:brief')
    builder.button(text='🔍 Зацепки', callback_data='assistant:clues')
    builder.button(text='🎁 Общая добыча', callback_data='assistant:loot_player')
    builder.button(text='🎲 Инициатива', callback_data='player:initiative')
    builder.button(text='⬅️ К профилю', callback_data='player:profile')
    builder.adjust(3, 2, 1, 1, 1)
    return builder.as_markup()


def dice_result_keyboard(expression: str, modifier: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    modifier_text = f'{int(modifier):+d}' if modifier else ''
    builder.button(text='🔁 Повторить', callback_data=f'dice:roll:{expression}')
    builder.button(text='⬆️ Преимущество', callback_data=f'dice:roll:adv{modifier_text}')
    builder.button(text='⬇️ Помеха', callback_data=f'dice:roll:dis{modifier_text}')
    builder.adjust(1, 2)
    return builder.as_markup()


def player_initiative_keyboard(can_roll: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if can_roll:
        builder.button(text='🎲 Бросить инициативу', callback_data='player:initiative_roll')
    builder.button(text='🔄 Обновить', callback_data='player:initiative')
    builder.button(text='⬅️ К профилю', callback_data='player:profile')
    builder.adjust(1)
    return builder.as_markup()


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



def admin_characters_keyboard(characters: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for character in characters:
        builder.button(
            text=f'{character["display_name"]} | ур. {character.get("level", 1)} | 🪙 {character["gold"]}',
            callback_data=f'admin:character:{character["id"]}',
        )
    builder.button(text='🧙 Создать персонажа', callback_data='admin:create_character')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def admin_character_manage_keyboard(character: dict) -> InlineKeyboardMarkup:
    character_id = int(character['id'])
    builder = InlineKeyboardBuilder()
    builder.button(text='✏️ Имя', callback_data=f'admin:edit_character:display_name:{character_id}')
    builder.button(text='🔑 Логин', callback_data=f'admin:edit_character:login:{character_id}')
    builder.button(text='🔒 Пароль', callback_data=f'admin:edit_character:password:{character_id}')
    builder.button(text='⭐ XP', callback_data=f'admin:edit_character:xp:{character_id}')
    builder.button(text='💰 Монеты', callback_data=f'admin:edit_character:gold:{character_id}')
    builder.button(text='💪 Сила', callback_data=f'admin:edit_character:strength_score:{character_id}')
    builder.button(text='🎒 Лимит кг', callback_data=f'admin:edit_character:max_carry_kg:{character_id}')
    builder.button(text='📝 Заметки мастера', callback_data=f'admin:edit_character_notes:{character_id}')
    builder.button(text='📖 Журнал', callback_data=f'admin:character_journal:{character_id}')
    builder.button(text='📚 Лист персонажа', callback_data=f'admin:sheet:{character_id}')
    builder.button(text='🗑️ Удалить персонажа', callback_data=f'admin:delete_character:{character_id}')
    builder.button(text='👥 Все персонажи', callback_data='admin:characters')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def character_sheet_sections_keyboard(
    section_counts: dict[str, int],
    prefix: str,
    character_id: int | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for section, title in SECTION_LABELS.items():
        count = int(section_counts.get(section, 0))
        if count <= 0:
            continue
        callback = f'{prefix}:sheet_section:{section}'
        if character_id is not None:
            callback = f'{prefix}:sheet_section:{character_id}:{section}'
        builder.button(text=f'{title} ({count})', callback_data=callback)
    back = 'player:profile' if prefix == 'player' else f'admin:character:{character_id}'
    builder.button(text='⬅️ Назад', callback_data=back)
    builder.adjust(1)
    return builder.as_markup()


def character_sheet_entries_keyboard(
    entries: list[dict],
    prefix: str,
    section: str,
    character_id: int | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for entry in entries:
        callback = f'{prefix}:sheet_entry:{entry["id"]}'
        if character_id is not None:
            callback = f'{prefix}:sheet_entry:{character_id}:{entry["id"]}'
        builder.button(text=entry['name'][:55], callback_data=callback)
    back = f'{prefix}:sheet'
    if character_id is not None:
        back = f'{prefix}:sheet:{character_id}'
    builder.button(text='⬅️ К разделам', callback_data=back)
    builder.adjust(1)
    return builder.as_markup()


def character_sheet_entry_keyboard(
    prefix: str,
    section: str,
    character_id: int | None = None,
) -> InlineKeyboardMarkup:
    callback = f'{prefix}:sheet_section:{section}'
    if character_id is not None:
        callback = f'{prefix}:sheet_section:{character_id}:{section}'
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text='⬅️ К списку', callback_data=callback)]]
    )


def character_conditions_keyboard(character_id: int, active_conditions: list[str]) -> InlineKeyboardMarkup:
    active = set(active_conditions)
    builder = InlineKeyboardBuilder()
    for value, title in CHARACTER_CONDITIONS:
        marker = '✅' if value in active else '▫️'
        builder.button(text=f'{marker} {title}', callback_data=f'admin:condition_toggle:{character_id}:{value}')
    builder.button(text='⬅️ К персонажу', callback_data=f'admin:character:{character_id}')
    builder.adjust(1)
    return builder.as_markup()


def admin_delete_character_confirm_keyboard(character_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Да, удалить персонажа', callback_data=f'admin:delete_character_confirm:{character_id}')
    builder.button(text='Нет, вернуться', callback_data=f'admin:character:{character_id}')
    builder.adjust(1)
    return builder.as_markup()


def character_session_select_keyboard(sessions: list[dict], character_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for session in sessions:
        builder.button(text=session['title'], callback_data=f'admin:character_session_set:{character_id}:{session["id"]}')
    builder.button(text='⬅️ К персонажу', callback_data=f'admin:character:{character_id}')
    builder.adjust(1)
    return builder.as_markup()

def items_keyboard(items: list[dict], action: str, back_callback: str = 'menu:main') -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        active_mark = '' if item.get('is_active', 1) else '🚫 '
        quantity_text = f' ×{item["quantity"]}' if 'quantity' in item else ''
        stock_text = f' | {stock_label(item)}' if 'shop_quantity' in item else ''
        category_text = f'{item.get("category_title") or category_label(item.get("category"))} | ' if 'category' in item else ''
        builder.button(
            text=f'{active_mark}{category_text}{item["name"]}{quantity_text} — {item["price"]} 🪙{stock_text}',
            callback_data=f'{action}:{item["id"]}',
        )
    builder.button(text='⬅️ Назад', callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()


def _category_value(category) -> str:
    if isinstance(category, dict):
        return str(category.get('value') or 'other')
    return str(category or 'other')


def _category_title(category) -> str:
    if isinstance(category, dict):
        return str(category.get('title') or category_label(category.get('value')))
    return category_label(str(category or 'other'))


def categories_keyboard(
    categories: list,
    action: str,
    back_callback: str = 'menu:main',
    include_all: bool = True,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if include_all:
        builder.button(text='📚 Все категории', callback_data=f'{action}:all')
    ordered = sorted(
        categories,
        key=lambda category: (CATEGORY_ORDER.get(_category_value(category), 999), _category_title(category).lower()),
    )
    seen = set()
    for category in ordered:
        value = _category_value(category)
        if value in seen:
            continue
        seen.add(value)
        builder.button(text=_category_title(category), callback_data=f'{action}:{value}')
    builder.button(text='⬅️ Назад', callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()


def item_category_keyboard(action: str, back_callback: str = 'admin:menu', categories: list | None = None) -> InlineKeyboardMarkup:
    source = categories if categories is not None else [{'value': value, 'title': title} for title, value in CATEGORIES]
    return categories_keyboard(source, action, back_callback, include_all=False)



def shop_items_page_keyboard(
    items: list[dict],
    categories: list[dict],
    current_category: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    safe_page = max(0, page)
    safe_total = max(1, total_pages)

    for item in items:
        builder.button(
            text=f'{item["name"]} — {item["price"]} 🪙 | {stock_label(item)}',
            callback_data=f'shop:item:{item["id"]}:{current_category}:{safe_page}',
        )

    values = [_category_value(category) for category in categories]
    if values:
        current_index = values.index(current_category) if current_category in values else 0
        prev_category = values[(current_index - 1) % len(values)]
        next_category = values[(current_index + 1) % len(values)]
        builder.button(text='⬅️ Категория', callback_data=f'shop:cat:{prev_category}:0')
        builder.button(text='Категория ➡️', callback_data=f'shop:cat:{next_category}:0')

    if safe_total > 1:
        prev_page = max(0, safe_page - 1)
        next_page = min(safe_total - 1, safe_page + 1)
        builder.button(text='⬅️ Страница', callback_data=f'shop:cat:{current_category}:{prev_page}')
        builder.button(text=f'{safe_page + 1}/{safe_total}', callback_data='noop')
        builder.button(text='Страница ➡️', callback_data=f'shop:cat:{current_category}:{next_page}')

    builder.button(text='📚 Список категорий', callback_data='shop:categories')
    builder.button(text='🏠 Главное меню', callback_data='menu:main')
    builder.adjust(*([1] * len(items)), 2, 3, 1, 1)
    return builder.as_markup()


def give_items_page_keyboard(
    items: list[dict],
    categories: list[dict],
    current_category: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    safe_page = max(0, page)
    safe_total = max(1, total_pages)

    for item in items:
        active_mark = '' if item.get('is_active', 1) else '🚫 '
        builder.button(
            text=f'{active_mark}{item["name"]} — {item["price"]} 🪙 | {stock_label(item)}',
            callback_data=f'admin:give_item_id:{item["id"]}',
        )

    values = [_category_value(category) for category in categories]
    if values:
        current_index = values.index(current_category) if current_category in values else 0
        prev_category = values[(current_index - 1) % len(values)]
        next_category = values[(current_index + 1) % len(values)]
        builder.button(text='⬅️ Категория', callback_data=f'admin:give_page:{prev_category}:0')
        builder.button(text='Категория ➡️', callback_data=f'admin:give_page:{next_category}:0')

    if safe_total > 1:
        prev_page = max(0, safe_page - 1)
        next_page = min(safe_total - 1, safe_page + 1)
        builder.button(text='⬅️ Страница', callback_data=f'admin:give_page:{current_category}:{prev_page}')
        builder.button(text=f'{safe_page + 1}/{safe_total}', callback_data='noop')
        builder.button(text='Страница ➡️', callback_data=f'admin:give_page:{current_category}:{next_page}')

    builder.button(text='📚 Список категорий', callback_data='admin:give_categories')
    builder.button(text='👥 Сменить персонажа', callback_data='admin:give_item')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(*([1] * len(items)), 2, 3, 1, 1, 1)
    return builder.as_markup()


def admin_items_page_keyboard(items: list[dict], page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    safe_page = max(0, page)
    safe_total = max(1, total_pages)
    for item in items:
        active_mark = '✅' if item.get('is_active', 1) else '🚫'
        category_text = item.get('category_title') or category_label(item.get('category'))
        builder.button(
            text=f'#{item["id"]} {active_mark} {category_text} | {item["name"]}',
            callback_data=f'admin:item:{item["id"]}',
        )
    if safe_total > 1:
        builder.button(text='⬅️ Страница', callback_data=f'admin:items_page:{max(0, safe_page - 1)}')
        builder.button(text=f'{safe_page + 1}/{safe_total}', callback_data='noop')
        builder.button(text='Страница ➡️', callback_data=f'admin:items_page:{min(safe_total - 1, safe_page + 1)}')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(*([1] * len(items)), 3, 1)
    return builder.as_markup()


def admin_categories_keyboard(categories: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='➕ Создать категорию', callback_data='admin:create_category')
    builder.button(text='🧭 Распределить предметы', callback_data='admin:auto_categorize_items')
    for category in categories:
        builder.button(text=_category_title(category), callback_data=f'admin:category:{_category_value(category)}')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def admin_category_details_keyboard(category_value: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='🗑️ Удалить категорию', callback_data=f'admin:delete_category:{category_value}')
    builder.button(text='📂 Все категории', callback_data='admin:categories')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def item_details_keyboard(item_id: int, can_buy: bool = True, back_callback: str = 'shop:list') -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if can_buy:
        builder.button(text='Купить ×1', callback_data=f'shop:buy:{item_id}:1')
    builder.button(text='⬅️ Магазин', callback_data=back_callback)
    builder.button(text='🏠 Главное меню', callback_data='menu:main')
    builder.adjust(1)
    return builder.as_markup()


def inventory_item_keyboard(
    item_id: int,
    can_sell: bool = True,
    can_use: bool = False,
    can_equip: bool = False,
    is_equipped: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if can_use:
        builder.button(text='Использовать ×1', callback_data=f'inventory:use_confirm:{item_id}')
    if can_equip:
        if is_equipped:
            builder.button(text='Снять экипировку', callback_data=f'inventory:unequip:{item_id}')
        else:
            builder.button(text='Экипировать', callback_data=f'inventory:equip:{item_id}')
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
    builder.button(text='✏️ Название', callback_data=f'admin:edit_item:name:{item_id}')
    builder.button(text='📝 Описание / свойства', callback_data=f'admin:edit_item:description:{item_id}')
    builder.button(text='💰 Цена покупки', callback_data=f'admin:edit_item:price:{item_id}')
    builder.button(text='💸 Цена продажи', callback_data=f'admin:edit_item:sell_price:{item_id}')
    builder.button(text='⚖️ Вес кг', callback_data=f'admin:edit_item:weight_kg:{item_id}')
    builder.button(text='🎒 Бонус кг', callback_data=f'admin:edit_item:carry_bonus_kg:{item_id}')
    builder.button(text='🐢 Штраф скорости', callback_data=f'admin:edit_item:speed_penalty:{item_id}')
    if item.get('is_consumable'):
        builder.button(text='🧪 Сделать нерасходным', callback_data=f'admin:toggle_consumable:{item_id}')
    else:
        builder.button(text='🧪 Сделать расходником', callback_data=f'admin:toggle_consumable:{item_id}')
    builder.button(text=f'🎽 Слот: {equipment_slot_label(item.get("equipment_slot"))}', callback_data=f'admin:equipment_slot:{item_id}')
    builder.button(text='⭐ Редкость', callback_data=f'admin:edit_item_rarity:{item_id}')
    builder.button(text='📂 Категория', callback_data=f'admin:edit_item_category:{item_id}')
    builder.button(text='🖼️ Картинка', callback_data=f'admin:edit_item_photo:{item_id}')
    builder.button(text='🔢 Остаток', callback_data=f'admin:set_stock:{item_id}')
    builder.button(text='🗑️ Удалить предмет', callback_data=f'admin:delete_item:{item_id}')
    builder.button(text='📦 Все предметы', callback_data='admin:items')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def admin_delete_item_confirm_keyboard(item_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Да, удалить', callback_data=f'admin:delete_item_confirm:{item_id}')
    builder.button(text='Нет, вернуться к предмету', callback_data=f'admin:item:{item_id}')
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


def item_equipment_slot_keyboard(item_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Не экипируется', callback_data=f'admin:set_equipment_slot:{item_id}:none')
    for value, title in EQUIPMENT_SLOTS:
        builder.button(text=title, callback_data=f'admin:set_equipment_slot:{item_id}:{value}')
    builder.button(text='⬅️ К предмету', callback_data=f'admin:item:{item_id}')
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



def sessions_keyboard(sessions: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='➕ Создать сессию', callback_data='admin:create_session')
    builder.button(text='👥 Распределить персонажей', callback_data='admin:assign_characters')
    for session in sessions:
        marker = '✅' if session.get('is_active', 1) else '🚫'
        builder.button(text=f'{marker} {session["title"]}', callback_data=f'admin:session:{session["id"]}')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def session_details_keyboard(session_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='⚡ Выдать XP и золото всей сессии', callback_data=f'admin:quick_reward_session:{session_id}')
    builder.button(text='➕ Добавить персонажа в эту сессию', callback_data=f'admin:session_assign:{session_id}')
    builder.button(text='🎲 Все сессии', callback_data='admin:sessions')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def admin_initiative_keyboard(encounter_id: int, session_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='➡️ Следующий ход', callback_data=f'admin:initiative_next:{encounter_id}:{session_id}')
    builder.button(text='🔄 Обновить', callback_data=f'admin:initiative_view:{session_id}')
    builder.button(text='⏹️ Завершить', callback_data=f'admin:initiative_end:{encounter_id}:{session_id}')
    builder.button(text='⬅️ К сессии', callback_data=f'admin:session:{session_id}')
    builder.adjust(1)
    return builder.as_markup()


def notify_sessions_keyboard(sessions: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for session in sessions:
        marker = '✅' if session.get('is_active', 1) else '🚫'
        builder.button(
            text=f'{marker} {session["title"]} ({session.get("characters_count", 0)})',
            callback_data=f'admin:notify_session:{session["id"]}',
        )
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def rest_sessions_keyboard(sessions: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for session in sessions:
        builder.button(
            text=f'{session["title"]} | персонажей: {session.get("characters_count", 0)}',
            callback_data=f'admin:rest_session:{session["id"]}',
        )
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def rest_type_keyboard(session_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='Короткий отдых', callback_data=f'admin:rest_type:{session_id}:short')
    builder.button(text='Долгий отдых', callback_data=f'admin:rest_type:{session_id}:long')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def assign_character_keyboard(characters: list[dict], back_callback: str = 'admin:sessions') -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for character in characters:
        builder.button(
            text=f'{character["display_name"]} | сейчас: {character.get("session_title") or "Без сессии"}',
            callback_data=f'admin:assign_character:{character["id"]}',
        )
    builder.button(text='⬅️ Назад', callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()


def session_select_keyboard(sessions: list[dict], character_id: int, back_callback: str = 'admin:assign_characters') -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for session in sessions:
        builder.button(text=session['title'], callback_data=f'admin:set_character_session:{character_id}:{session["id"]}')
    builder.button(text='⬅️ Назад', callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()


def session_assign_characters_keyboard(session_id: int, characters: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for character in characters:
        current = character.get('session_title') or 'Без сессии'
        builder.button(text=f'{character["display_name"]} | сейчас: {current}', callback_data=f'admin:set_character_session:{character["id"]}:{session_id}')
    builder.button(text='⬅️ К сессии', callback_data=f'admin:session:{session_id}')
    builder.adjust(1)
    return builder.as_markup()

def quests_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text='➕ Создать квест', callback_data='admin:create_quest')
    builder.button(text='📜 Список квестов', callback_data='admin:quest_list')
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def quick_reward_sessions_keyboard(sessions: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for session in sessions:
        builder.button(
            text=f'{session["title"]} | персонажей: {session.get("characters_count", 0)}',
            callback_data=f'admin:quick_reward_session:{session["id"]}',
        )
    builder.button(text='⬅️ Админ-панель', callback_data='admin:menu')
    builder.adjust(1)
    return builder.as_markup()


def quick_reward_presets_keyboard(session_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, preset in QUICK_REWARD_PRESETS.items():
        builder.button(
            text=f'{preset["title"]}: {preset["xp"]} XP, {preset["gold"]} 🪙 каждому',
            callback_data=f'admin:quick_reward_apply:{session_id}:{key}',
        )
    builder.button(text='⬅️ Выбрать сессию', callback_data='admin:quick_rewards')
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
        builder.button(text=f'{item.get("category_title") or category_label(item.get("category"))} | {item["name"]} — {item["price"]} 🪙', callback_data=f'quest_item:{item["id"]}')
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
