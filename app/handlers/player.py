from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database import Database
from app.keyboards import (
    back_to_main_menu,
    characters_select_keyboard,
    inventory_item_keyboard,
    item_details_keyboard,
    items_keyboard,
    stock_label,
    transfer_menu,
)
from app.levels import level_progress_text, levels_table_text
from app.states import TransferGoldState, TransferItemState
from app.ui import edit_or_answer

router = Router(name='player')


def item_text(item: dict, quantity: int | None = None) -> str:
    qty_line = f'Количество в инвентаре: <b>{quantity}</b>\n' if quantity is not None else ''
    if item.get('is_active', 1):
        availability = f'В магазине: <b>{stock_label(item)}</b>'
    else:
        availability = 'В магазине: <b>нельзя купить</b>'
    return (
        f'<b>{item["name"]}</b>\n'
        f'{qty_line}'
        f'Редкость: <b>{item["rarity"]}</b>\n'
        f'Цена: <b>{item["price"]}</b> 🪙\n'
        f'{availability}\n\n'
        f'{item["description"] or "Описание пока не добавлено."}'
    )


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
    characters = await db.list_characters()
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
    await message.answer(result, reply_markup=back_to_main_menu())


@router.message(Command('profile'))
async def profile_command(message: Message, db: Database) -> None:
    character = await require_character(message, db)
    if character is None:
        return
    await message.answer(
        f'👤 <b>{character["display_name"]}</b>\n'
        f'Логин: <code>{character["login"]}</code>\n\n'
        f'{level_progress_text(character)}\n'
        f'Монеты: <b>{character["gold"]}</b> 🪙',
        reply_markup=back_to_main_menu(),
    )


@router.callback_query(F.data == 'player:profile')
async def profile_callback(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    await edit_or_answer(
        callback.message,
        f'👤 <b>{character["display_name"]}</b>\n'
        f'Логин: <code>{character["login"]}</code>\n\n'
        f'{level_progress_text(character)}\n'
        f'Монеты: <b>{character["gold"]}</b> 🪙',
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
    text = '🎒 <b>Инвентарь</b>\n\n' + '\n'.join(
        f'• <b>{item["name"]}</b> ×{item["quantity"]} — {item["rarity"]}, продать за {item["price"]} 🪙'
        for item in inventory
    )
    await edit_or_answer(callback.message, text, reply_markup=items_keyboard(inventory, 'inventory:item', 'menu:main'))
    await callback.answer()


async def send_inventory(message: Message, db: Database, character: dict) -> None:
    inventory = await db.list_inventory(character['id'])
    if not inventory:
        await message.answer('🎒 Инвентарь пуст.', reply_markup=back_to_main_menu())
        return
    text = '🎒 <b>Инвентарь</b>\n\n' + '\n'.join(
        f'• <b>{item["name"]}</b> ×{item["quantity"]} — {item["rarity"]}, продать за {item["price"]} 🪙'
        for item in inventory
    )
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
    if item.get('image_file_id'):
        await callback.message.answer_photo(
            item['image_file_id'],
            caption=text,
            reply_markup=inventory_item_keyboard(item_id),
        )
    else:
        await callback.message.answer(text, reply_markup=inventory_item_keyboard(item_id))
    await callback.answer()


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


@router.callback_query(F.data == 'shop:list')
async def shop_callback(callback: CallbackQuery, db: Database) -> None:
    items = await db.list_items(only_active=True)
    if not items:
        await edit_or_answer(callback.message, '🛒 Магазин пока пуст.', reply_markup=back_to_main_menu())
        await callback.answer()
        return
    await edit_or_answer(
        callback.message,
        '🛒 <b>Магазин</b>\nВыбери предмет, чтобы посмотреть описание, картинку и остаток:',
        reply_markup=items_keyboard(items, 'shop:item', 'menu:main'),
    )
    await callback.answer()


async def send_shop(message: Message, db: Database) -> None:
    items = await db.list_items(only_active=True)
    if not items:
        await message.answer('🛒 Магазин пока пуст.', reply_markup=back_to_main_menu())
        return
    await message.answer(
        '🛒 <b>Магазин</b>\nВыбери предмет, чтобы посмотреть описание, картинку и остаток:',
        reply_markup=items_keyboard(items, 'shop:item', 'menu:main'),
    )


@router.callback_query(F.data.startswith('shop:item:'))
async def shop_item_callback(callback: CallbackQuery, db: Database) -> None:
    item_id = int(callback.data.split(':')[2])
    item = await db.get_item(item_id)
    if item is None or not item['is_active']:
        await callback.answer('Предмет не найден.', show_alert=True)
        return
    text = item_text(item)
    can_buy = int(item.get('shop_quantity', -1)) != 0
    if item.get('image_file_id'):
        await callback.message.answer_photo(
            item['image_file_id'],
            caption=text,
            reply_markup=item_details_keyboard(item_id, can_buy=can_buy),
        )
    else:
        await callback.message.answer(text, reply_markup=item_details_keyboard(item_id, can_buy=can_buy))
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
        await callback.message.answer(
            f'{message}\n'
            f'Остаток в магазине: <b>{stock_label(item)}</b>\n\n'
            f'Текущий баланс: <b>{updated["gold"]}</b> 🪙',
            reply_markup=back_to_main_menu(),
        )
