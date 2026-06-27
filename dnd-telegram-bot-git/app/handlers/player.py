from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.database import Database
from app.keyboards import back_to_main_menu, item_details_keyboard, items_keyboard
from app.ui import edit_or_answer

router = Router(name='player')


def item_text(item: dict, quantity: int | None = None) -> str:
    qty_line = f'Количество: <b>{quantity}</b>\n' if quantity is not None else ''
    return (
        f'<b>{item["name"]}</b>\n'
        f'{qty_line}'
        f'Редкость: <b>{item["rarity"]}</b>\n'
        f'Цена: <b>{item["price"]}</b> 🪙\n\n'
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


@router.message(Command('profile'))
async def profile_command(message: Message, db: Database) -> None:
    character = await require_character(message, db)
    if character is None:
        return
    await message.answer(
        f'👤 <b>{character["display_name"]}</b>\n'
        f'Логин: <code>{character["login"]}</code>\n'
        f'XP: <b>{character["xp"]}</b>\n'
        f'Монеты: <b>{character["gold"]}</b> 🪙',
        reply_markup=back_to_main_menu(),
    )


@router.callback_query(F.data == 'player:profile')
async def profile_callback(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    await edit_or_answer(callback.message, 
        f'👤 <b>{character["display_name"]}</b>\n'
        f'Логин: <code>{character["login"]}</code>\n'
        f'XP: <b>{character["xp"]}</b>\n'
        f'Монеты: <b>{character["gold"]}</b> 🪙',
        reply_markup=back_to_main_menu(),
    )
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
        f'• <b>{item["name"]}</b> ×{item["quantity"]} — {item["rarity"]}' for item in inventory
    )
    await edit_or_answer(callback.message, text, reply_markup=items_keyboard(inventory, 'inventory:item', 'menu:main'))
    await callback.answer()


async def send_inventory(message: Message, db: Database, character: dict) -> None:
    inventory = await db.list_inventory(character['id'])
    if not inventory:
        await message.answer('🎒 Инвентарь пуст.', reply_markup=back_to_main_menu())
        return
    text = '🎒 <b>Инвентарь</b>\n\n' + '\n'.join(
        f'• <b>{item["name"]}</b> ×{item["quantity"]} — {item["rarity"]}' for item in inventory
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
            reply_markup=back_to_main_menu(),
        )
    else:
        await callback.message.answer(text, reply_markup=back_to_main_menu())
    await callback.answer()


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
    await edit_or_answer(callback.message, 
        '🛒 <b>Магазин</b>\nВыбери предмет, чтобы посмотреть описание и картинку:',
        reply_markup=items_keyboard(items, 'shop:item', 'menu:main'),
    )
    await callback.answer()


async def send_shop(message: Message, db: Database) -> None:
    items = await db.list_items(only_active=True)
    if not items:
        await message.answer('🛒 Магазин пока пуст.', reply_markup=back_to_main_menu())
        return
    await message.answer(
        '🛒 <b>Магазин</b>\nВыбери предмет, чтобы посмотреть описание и картинку:',
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
    if item.get('image_file_id'):
        await callback.message.answer_photo(
            item['image_file_id'],
            caption=text,
            reply_markup=item_details_keyboard(item_id),
        )
    else:
        await callback.message.answer(text, reply_markup=item_details_keyboard(item_id))
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
        await callback.message.answer(
            f'{message}\n\nТекущий баланс: <b>{updated["gold"]}</b> 🪙',
            reply_markup=back_to_main_menu(),
        )
