from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database import Database, default_sell_price
from app.item_rules import equipment_slot_label
from app.keyboards import (
    PAGE_SIZE,
    back_to_main_menu,
    categories_keyboard,
    category_label,
    characters_select_keyboard,
    inventory_item_keyboard,
    item_details_keyboard,
    items_keyboard,
    shop_items_page_keyboard,
    stock_label,
    transfer_menu,
)
from app.levels import level_progress_text, levels_table_text
from app.states import TransferGoldState, TransferItemState
from app.ui import answer_with_optional_photo, edit_or_answer

router = Router(name='player')


def item_text(item: dict, quantity: int | None = None) -> str:
    qty_line = f'Количество в инвентаре: <b>{quantity}</b>\n' if quantity is not None else ''
    if item.get('is_active', 1):
        availability = f'В магазине: <b>{stock_label(item)}</b>'
    else:
        availability = 'В магазине: <b>нельзя купить</b>'
    weight = float(item.get('weight_kg') or 0)
    total_weight_line = ''
    if quantity is not None:
        total_weight_line = f'Общий вес: <b>{weight * int(quantity):.2f}</b> кг\n'
    use_line = 'Тип: <b>расходник</b>\n' if item.get('is_consumable') else ''
    slot = str(item.get('equipment_slot') or '').strip()
    equipment_line = f'Экипировка: <b>{equipment_slot_label(slot)}</b>\n' if slot else ''
    equipped_line = 'Статус: <b>экипировано</b>\n' if item.get('is_equipped') else ''
    carry_bonus = float(item.get('carry_bonus_kg') or 0)
    carry_bonus_line = f'Бонус переносимого веса: <b>+{carry_bonus:.1f}</b> кг\n' if carry_bonus > 0 else ''
    speed_penalty = int(item.get('speed_penalty') or 0)
    speed_penalty_line = f'Штраф скорости: <b>-{speed_penalty}</b>\n' if speed_penalty > 0 else ''
    price = int(item.get('price') or 0)
    sell_price = int(item.get('sell_price') or 0) or default_sell_price(price)
    return (
        f'<b>{item["name"]}</b>\n'
        f'{qty_line}'
        f'Категория: <b>{item.get("category_title") or category_label(item.get("category"))}</b>\n'
        f'Редкость: <b>{item["rarity"]}</b>\n'
        f'{use_line}'
        f'{equipment_line}'
        f'{equipped_line}'
        f'{carry_bonus_line}'
        f'{speed_penalty_line}'
        f'Вес: <b>{weight:.2f}</b> кг\n'
        f'{total_weight_line}'
        f'Цена покупки: <b>{price}</b> 🪙\n'
        f'Цена продажи: <b>{sell_price}</b> 🪙\n'
        f'{availability}\n\n'
        f'{item["description"] or "Описание пока не добавлено."}'
    )


def carry_info_text(carry: dict | None) -> str:
    if not carry:
        return 'Вес инвентаря: данные недоступны.'
    warning = '\n⚠️ <b>Вы несете слишком много</b>' if carry.get('overloaded') else ''
    free = float(carry.get('free_weight_kg', 0))
    free_line = f'Свободно: <b>{free:.2f}</b> кг' if free >= 0 else f'Перегруз: <b>{abs(free):.2f}</b> кг'
    carry_bonus = float(carry.get('carry_bonus_kg') or 0)
    carry_bonus_line = f'\nБонус от сумок: <b>+{carry_bonus:.1f}</b> кг' if carry_bonus > 0 else ''
    speed_penalty = int(carry.get('speed_penalty') or 0)
    speed_penalty_line = f'\nШтраф скорости: <b>-{speed_penalty}</b>' if speed_penalty > 0 else ''
    return (
        f'Сила: <b>{carry.get("strength_score", 10)}</b>\n'
        f'Базовый лимит: <b>{float(carry.get("base_carry_kg", carry.get("max_carry_kg", 0))):.1f}</b> кг'
        f'{carry_bonus_line}{speed_penalty_line}\n'
        f'Инвентарь: <b>{float(carry.get("current_weight_kg", 0)):.2f}</b> кг / '
        f'<b>{float(carry.get("max_carry_kg", 0)):.1f}</b> кг\n'
        f'{free_line}'
        f'{warning}'
    )


def equipment_text(equipment: list[dict]) -> str:
    if not equipment:
        return 'Экипировка: <b>ничего не экипировано</b>'
    lines = ['🧍 <b>Экипировка</b>']
    for item in equipment:
        carry_bonus = float(item.get('carry_bonus_kg') or 0)
        speed_penalty = int(item.get('speed_penalty') or 0)
        effects = []
        if carry_bonus > 0:
            effects.append(f'+{carry_bonus:.1f} кг к переносимому весу')
        if speed_penalty > 0:
            effects.append(f'-{speed_penalty} скорости')
        effect_text = f' ({", ".join(effects)})' if effects else ''
        lines.append(
            f'• {equipment_slot_label(item.get("slot"))}: <b>{item["name"]}</b>{effect_text} — '
            f'{item["description"] or "свойства не описаны"}'
        )
    return '\n'.join(lines)


async def profile_text(character: dict, db: Database) -> str:
    carry = await db.get_character_carry_info(int(character['id']))
    equipment = await db.list_equipment(int(character['id']))
    return (
        f'👤 <b>{character["display_name"]}</b>\n'
        f'Логин: <code>{character["login"]}</code>\n'
        f'Сессия: <b>{character.get("session_title") or "Без сессии"}</b>\n\n'
        f'{level_progress_text(character)}\n'
        f'Монеты: <b>{character["gold"]}</b> 🪙\n\n'
        f'🎒 <b>Вес и перенос</b>\n{carry_info_text(carry)}\n\n'
        f'{equipment_text(equipment)}'
    )


async def inventory_text(character: dict, db: Database, inventory: list[dict]) -> str:
    carry = await db.get_character_carry_info(int(character['id']))
    lines = []
    for item in inventory:
        weight = float(item.get('weight_kg') or 0)
        quantity = int(item['quantity'])
        marks = []
        if item.get('is_equipped'):
            marks.append('экипировано')
        if item.get('is_consumable'):
            marks.append('расходник')
        if item.get('equipment_slot'):
            marks.append(equipment_slot_label(item.get('equipment_slot')))
        if float(item.get('carry_bonus_kg') or 0) > 0:
            marks.append(f'+{float(item.get("carry_bonus_kg") or 0):.1f} кг')
        if int(item.get('speed_penalty') or 0) > 0:
            marks.append(f'-{int(item.get("speed_penalty") or 0)} скорости')
        marks_text = f' ({", ".join(marks)})' if marks else ''
        sell_price = int(item.get('sell_price') or 0) or default_sell_price(int(item.get('price') or 0))
        lines.append(
            f'• {item.get("category_title") or category_label(item.get("category"))} | '
            f'<b>{item["name"]}</b> ×{quantity}{marks_text} — {item["rarity"]}, '
            f'{weight * quantity:.2f} кг, продать за {sell_price} 🪙'
        )
    return '🎒 <b>Инвентарь</b>\n\n' + carry_info_text(carry) + '\n\n' + '\n'.join(lines)


async def require_character(message_or_callback, db: Database) -> dict | None:
    user_id = message_or_callback.from_user.id
    character = await db.get_character_by_telegram_id(user_id)
    if character is None:
        target = message_or_callback.message if isinstance(message_or_callback, CallbackQuery) else message_or_callback
        await target.answer('Сначала нужно войти в персонажа: /login')
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.answer()
        return None
    return character


async def other_characters(db: Database, current_character_id: int) -> list[dict]:
    current = await db.get_character(current_character_id)
    if current is None:
        return []
    characters = await db.list_characters(session_id=current.get('session_id'))
    return [character for character in characters if int(character['id']) != int(current_character_id)]


@router.message(Command('transfer'))
async def transfer_command(message: Message, db: Database) -> None:
    character = await require_character(message, db)
    if character is None:
        return
    await message.answer('🔁 Что хочешь передать другому игроку?', reply_markup=transfer_menu())


@router.callback_query(F.data == 'transfer:menu')
async def transfer_menu_callback(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    await edit_or_answer(callback.message, '🔁 Что хочешь передать другому игроку?', reply_markup=transfer_menu())
    await callback.answer()


@router.callback_query(F.data == 'transfer:gold')
async def transfer_gold_select_recipient(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    recipients = await other_characters(db, character['id'])
    if not recipients:
        await edit_or_answer(callback.message, 'Пока нет других персонажей для передачи монет.', reply_markup=back_to_main_menu())
        await callback.answer()
        return
    await state.clear()
    await state.update_data(sender_id=character['id'])
    await edit_or_answer(callback.message, 'Кому передать монеты?', reply_markup=characters_select_keyboard(recipients, 'transfer_gold_to', 'transfer:menu'))
    await callback.answer()


@router.callback_query(F.data.startswith('transfer_gold_to:'))
async def transfer_gold_enter_amount(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    recipient_id = int(callback.data.split(':')[1])
    await state.update_data(sender_id=character['id'], recipient_id=recipient_id)
    await state.set_state(TransferGoldState.amount)
    await callback.message.answer('Введи количество монет для передачи. Например: <code>25</code>')
    await callback.answer()


@router.message(TransferGoldState.amount)
async def transfer_gold_finish(message: Message, state: FSMContext, db: Database) -> None:
    character = await require_character(message, db)
    if character is None:
        return
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer('Нужно ввести целое число. Например: <code>25</code>')
        return
    data = await state.get_data()
    success, result = await db.transfer_gold(character['id'], int(data['recipient_id']), amount)
    await state.clear()
    updated = await db.get_character(character['id'])
    await message.answer(
        f'{result}\n\nТвой баланс: <b>{updated["gold"]}</b> 🪙',
        reply_markup=back_to_main_menu(),
    )


@router.callback_query(F.data == 'transfer:item')
async def transfer_item_select_item(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    inventory = await db.list_inventory(character['id'])
    if not inventory:
        await edit_or_answer(callback.message, 'У тебя пока нет предметов для передачи.', reply_markup=back_to_main_menu())
        await callback.answer()
        return
    await state.clear()
    await state.update_data(sender_id=character['id'])
    await edit_or_answer(callback.message, 'Какой предмет передать?', reply_markup=items_keyboard(inventory, 'transfer:item_pick', 'transfer:menu'))
    await callback.answer()


@router.callback_query(F.data.startswith('inventory:transfer_start:'))
async def transfer_item_from_inventory(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    item_id = int(callback.data.split(':')[2])
    await state.clear()
    await state.update_data(sender_id=character['id'], item_id=item_id)
    recipients = await other_characters(db, character['id'])
    if not recipients:
        await callback.message.answer('Пока нет других персонажей для передачи предмета.', reply_markup=back_to_main_menu())
        await callback.answer()
        return
    await callback.message.answer('Кому передать предмет?', reply_markup=characters_select_keyboard(recipients, 'transfer_item_to', 'player:inventory'))
    await callback.answer()


@router.callback_query(F.data.startswith('transfer:item_pick:'))
async def transfer_item_select_recipient(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    item_id = int(callback.data.split(':')[2])
    recipients = await other_characters(db, character['id'])
    if not recipients:
        await edit_or_answer(callback.message, 'Пока нет других персонажей для передачи предмета.', reply_markup=back_to_main_menu())
        await callback.answer()
        return
    await state.update_data(sender_id=character['id'], item_id=item_id)
    await edit_or_answer(callback.message, 'Кому передать предмет?', reply_markup=characters_select_keyboard(recipients, 'transfer_item_to', 'transfer:menu'))
    await callback.answer()


@router.callback_query(F.data.startswith('transfer_item_to:'))
async def transfer_item_enter_quantity(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    recipient_id = int(callback.data.split(':')[1])
    await state.update_data(sender_id=character['id'], recipient_id=recipient_id)
    await state.set_state(TransferItemState.quantity)
    await callback.message.answer('Введи количество предметов для передачи. Например: <code>1</code>')
    await callback.answer()


@router.message(TransferItemState.quantity)
async def transfer_item_finish(message: Message, state: FSMContext, db: Database) -> None:
    character = await require_character(message, db)
    if character is None:
        return
    try:
        quantity = int(message.text.strip())
    except ValueError:
        await message.answer('Нужно ввести целое число. Например: <code>1</code>')
        return
    data = await state.get_data()
    success, result = await db.transfer_item(
        character['id'],
        int(data['recipient_id']),
        int(data['item_id']),
        quantity,
    )
    await state.clear()
    carry = await db.get_character_carry_info(character['id'])
    await message.answer(result + '\n\n🎒 <b>Твой вес после передачи</b>\n' + carry_info_text(carry), reply_markup=back_to_main_menu())


@router.message(Command('profile'))
async def profile_command(message: Message, db: Database) -> None:
    character = await require_character(message, db)
    if character is None:
        return
    await message.answer(await profile_text(character, db), reply_markup=back_to_main_menu())


@router.callback_query(F.data == 'player:profile')
async def profile_callback(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    await edit_or_answer(
        callback.message,
        await profile_text(character, db),
        reply_markup=back_to_main_menu(),
    )
    await callback.answer()


@router.message(Command('levels'))
async def levels_command(message: Message) -> None:
    await message.answer(levels_table_text(), reply_markup=back_to_main_menu())


@router.callback_query(F.data == 'player:levels')
async def levels_callback(callback: CallbackQuery) -> None:
    await edit_or_answer(callback.message, levels_table_text(), reply_markup=back_to_main_menu())
    await callback.answer()


@router.message(Command('inventory'))
async def inventory_command(message: Message, db: Database) -> None:
    character = await require_character(message, db)
    if character is None:
        return
    await send_inventory(message, db, character)


@router.callback_query(F.data == 'player:inventory')
async def inventory_callback(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    inventory = await db.list_inventory(character['id'])
    if not inventory:
        await edit_or_answer(callback.message, '🎒 Инвентарь пуст.', reply_markup=back_to_main_menu())
        await callback.answer()
        return
    text = await inventory_text(character, db, inventory)
    await edit_or_answer(callback.message, text, reply_markup=items_keyboard(inventory, 'inventory:item', 'menu:main'))
    await callback.answer()


async def send_inventory(message: Message, db: Database, character: dict) -> None:
    inventory = await db.list_inventory(character['id'])
    if not inventory:
        await message.answer('🎒 Инвентарь пуст.', reply_markup=back_to_main_menu())
        return
    text = await inventory_text(character, db, inventory)
    await message.answer(text, reply_markup=items_keyboard(inventory, 'inventory:item', 'menu:main'))


@router.callback_query(F.data.startswith('inventory:item:'))
async def inventory_item_callback(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    item_id = int(callback.data.split(':')[2])
    inventory = await db.list_inventory(character['id'])
    item = next((row for row in inventory if row['id'] == item_id), None)
    if item is None:
        await callback.answer('Предмет не найден в инвентаре.', show_alert=True)
        return
    text = item_text(item, quantity=item['quantity'])
    await answer_with_optional_photo(
        callback.message,
        text,
        reply_markup=inventory_item_keyboard(
            item_id,
            can_use=bool(item.get('is_consumable')),
            can_equip=bool(str(item.get('equipment_slot') or '').strip()),
            is_equipped=bool(item.get('is_equipped')),
        ),
        image_ref=item.get('image_file_id'),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('inventory:use:'))
async def use_item_callback(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    item_id = int(callback.data.split(':')[2])
    success, message = await db.use_item(character['id'], item_id)
    await callback.answer('Использовано ✅' if success else message, show_alert=not success)
    if not success:
        return
    carry = await db.get_character_carry_info(character['id'])
    await callback.message.answer(
        message + '\n\n🎒 <b>Вес после использования</b>\n' + carry_info_text(carry),
        reply_markup=back_to_main_menu(),
    )


@router.callback_query(F.data.startswith('inventory:equip:'))
async def equip_item_callback(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    item_id = int(callback.data.split(':')[2])
    success, message = await db.equip_item(character['id'], item_id)
    await callback.answer('Экипировано ✅' if success else message, show_alert=not success)
    if not success:
        return
    carry = await db.get_character_carry_info(character['id'])
    await callback.message.answer(
        message + '\n\n' + equipment_text(await db.list_equipment(character['id'])) + '\n\n🎒 <b>Перенос</b>\n' + carry_info_text(carry),
        reply_markup=back_to_main_menu(),
    )


@router.callback_query(F.data.startswith('inventory:unequip:'))
async def unequip_item_callback(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    item_id = int(callback.data.split(':')[2])
    success, message = await db.unequip_item(character['id'], item_id)
    await callback.answer('Снято ✅' if success else message, show_alert=not success)
    if not success:
        return
    carry = await db.get_character_carry_info(character['id'])
    await callback.message.answer(
        message + '\n\n' + equipment_text(await db.list_equipment(character['id'])) + '\n\n🎒 <b>Перенос</b>\n' + carry_info_text(carry),
        reply_markup=back_to_main_menu(),
    )


@router.callback_query(F.data.startswith('inventory:sell:'))
async def sell_item_callback(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    _, _, item_id_raw, quantity_raw = callback.data.split(':')
    success, message = await db.sell_item(character['id'], int(item_id_raw), int(quantity_raw))
    await callback.answer(message, show_alert=not success)
    if success:
        updated = await db.get_character(character['id'])
        await callback.message.answer(
            f'{message}\n\nТекущий баланс: <b>{updated["gold"]}</b> 🪙',
            reply_markup=back_to_main_menu(),
        )


@router.message(Command('shop'))
async def shop_command(message: Message, db: Database) -> None:
    await send_shop(message, db)


async def shop_header(
    db: Database,
    telegram_id: int | None = None,
    category: dict | None = None,
    page: int = 0,
    total_pages: int = 1,
) -> str:
    character = await db.get_character_by_telegram_id(telegram_id) if telegram_id else None
    balance_line = f'Твои монеты: <b>{character["gold"]}</b> 🪙\n' if character else ''
    category_line = f'Категория: <b>{category["title"]}</b>\n' if category else ''
    page_line = f'Страница: <b>{page + 1}/{max(1, total_pages)}</b>\n'
    return (
        '🛒 <b>Магазин</b>\n'
        f'{balance_line}'
        f'{category_line}'
        f'{page_line}\n'
        'Показываю по 10 предметов. Картинка открывается только в карточке предмета, чтобы бот не зависал.'
    )


def shop_items_text(items: list[dict]) -> str:
    if not items:
        return '\n\nВ этой категории сейчас нет предметов, которые можно купить.'
    lines = []
    for index, item in enumerate(items, start=1):
        lines.append(
            f'{index}. <b>{item["name"]}</b> — {item["price"]} 🪙 | {item["rarity"]} | {stock_label(item)}'
        )
    return '\n\n' + '\n'.join(lines)


async def render_shop_category(message: Message, db: Database, telegram_id: int, category_value: str | None = None, page: int = 0) -> None:
    categories = await db.list_categories(only_with_items=True, only_active=True, only_purchasable=True)
    if not categories:
        await edit_or_answer(message, '🛒 Магазин пока пуст или все предметы закончились.', reply_markup=back_to_main_menu())
        return

    category_values = [category['value'] for category in categories]
    if not category_value or category_value not in category_values:
        category_value = category_values[0]

    category = next(category for category in categories if category['value'] == category_value)
    total_items = await db.count_items(only_active=True, category=category_value, only_purchasable=True)
    total_pages = max(1, (total_items + PAGE_SIZE - 1) // PAGE_SIZE)
    safe_page = min(max(0, int(page)), total_pages - 1)
    items = await db.list_items(
        only_active=True,
        category=category_value,
        only_purchasable=True,
        limit=PAGE_SIZE,
        offset=safe_page * PAGE_SIZE,
    )
    text = await shop_header(db, telegram_id, category, safe_page, total_pages)
    text += shop_items_text(items)
    await edit_or_answer(
        message,
        text,
        reply_markup=shop_items_page_keyboard(items, categories, category_value, safe_page, total_pages),
    )


@router.callback_query(F.data == 'shop:list')
async def shop_callback(callback: CallbackQuery, db: Database) -> None:
    await render_shop_category(callback.message, db, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == 'shop:categories')
async def shop_categories_callback(callback: CallbackQuery, db: Database) -> None:
    categories = await db.list_categories(only_with_items=True, only_active=True, only_purchasable=True)
    if not categories:
        await edit_or_answer(callback.message, '🛒 Магазин пока пуст или все предметы закончились.', reply_markup=back_to_main_menu())
        await callback.answer()
        return
    await edit_or_answer(
        callback.message,
        '📚 <b>Категории магазина</b>\n\nВыбери категорию. Внутри будет максимум 10 предметов на странице.',
        reply_markup=categories_keyboard(categories, 'shop:category', 'menu:main', include_all=False),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('shop:category:'))
async def shop_category_callback(callback: CallbackQuery, db: Database) -> None:
    category = callback.data.split(':', 2)[2]
    await render_shop_category(callback.message, db, callback.from_user.id, category, 0)
    await callback.answer()


@router.callback_query(F.data.startswith('shop:cat:'))
async def shop_category_page_callback(callback: CallbackQuery, db: Database) -> None:
    _, _, category, page_raw = callback.data.split(':')
    await render_shop_category(callback.message, db, callback.from_user.id, category, int(page_raw))
    await callback.answer()


async def send_shop(message: Message, db: Database) -> None:
    categories = await db.list_categories(only_with_items=True, only_active=True, only_purchasable=True)
    if not categories:
        await message.answer('🛒 Магазин пока пуст или все предметы закончились.', reply_markup=back_to_main_menu())
        return
    category_value = categories[0]['value']
    total_items = await db.count_items(only_active=True, category=category_value, only_purchasable=True)
    total_pages = max(1, (total_items + PAGE_SIZE - 1) // PAGE_SIZE)
    items = await db.list_items(
        only_active=True,
        category=category_value,
        only_purchasable=True,
        limit=PAGE_SIZE,
        offset=0,
    )
    text = await shop_header(db, message.from_user.id, categories[0], 0, total_pages)
    text += shop_items_text(items)
    await message.answer(
        text,
        reply_markup=shop_items_page_keyboard(items, categories, category_value, 0, total_pages),
    )


@router.callback_query(F.data.startswith('shop:item:'))
async def shop_item_callback(callback: CallbackQuery, db: Database) -> None:
    parts = callback.data.split(':')
    item_id = int(parts[2])
    back_callback = 'shop:list'
    if len(parts) >= 5:
        back_callback = f'shop:cat:{parts[3]}:{parts[4]}'
    item = await db.get_item(item_id)
    if item is None or not item['is_active'] or int(item.get('shop_quantity', -1)) == 0:
        await callback.answer('Предмет не найден или сейчас недоступен для покупки.', show_alert=True)
        return
    text = item_text(item)
    await answer_with_optional_photo(
        callback.message,
        text,
        reply_markup=item_details_keyboard(item_id, can_buy=True, back_callback=back_callback),
        image_ref=item.get('image_file_id'),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('shop:buy:'))
async def buy_item_callback(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    _, _, item_id_raw, quantity_raw = callback.data.split(':')
    success, message = await db.buy_item(character['id'], int(item_id_raw), int(quantity_raw))
    await callback.answer(message, show_alert=not success)
    if success:
        updated = await db.get_character(character['id'])
        item = await db.get_item(int(item_id_raw))
        carry = await db.get_character_carry_info(character['id'])
        await callback.message.answer(
            f'{message}\n'
            f'Остаток в магазине: <b>{stock_label(item)}</b>\n\n'
            f'Текущий баланс: <b>{updated["gold"]}</b> 🪙\n\n'
            f'🎒 <b>Вес после покупки</b>\n{carry_info_text(carry)}',
            reply_markup=back_to_main_menu(),
        )
