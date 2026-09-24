from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.assistant_keyboards import (
    clues_admin_keyboard,
    condition_duration_keyboard,
    consumable_confirm_keyboard,
    death_saves_keyboard,
    group_loot_admin_keyboard,
    group_loot_characters_keyboard,
    operations_keyboard,
    search_filter_keyboard,
    search_results_keyboard,
    search_source_keyboard,
    undo_confirm_keyboard,
)
from app.config import Settings
from app.database import Database
from app.gameplay import condition_label, format_session_card
from app.handlers.common import is_admin
from app.handlers.player import carry_info_text, equipment_text, item_text, require_character
from app.keyboards import back_to_main_menu, inventory_item_keyboard, item_details_keyboard, session_card_keyboard
from app.states import CampaignClueState, ItemSearchState
from app.ui import answer_with_optional_photo, edit_or_answer


router = Router(name='assistant')


async def require_admin(event: Message | CallbackQuery, settings: Settings) -> bool:
    if is_admin(event.from_user.id, settings):
        return True
    target = event.message if isinstance(event, CallbackQuery) else event
    await target.answer('Эта функция доступна только администратору.')
    if isinstance(event, CallbackQuery):
        await event.answer()
    return False


def clues_text(clues: list[dict]) -> str:
    if not clues:
        return '🔍 <b>Зацепки</b>\n\nПока важных зацепок нет.'
    lines = ['🔍 <b>Зацепки</b>']
    for index, clue in enumerate(clues, 1):
        details = html.escape(str(clue.get('details') or '').strip())
        suffix = f' — {details}' if details else ''
        lines.append(f'{index}. <b>{html.escape(str(clue["title"]))}</b>{suffix}')
    return '\n'.join(lines)


def loot_text(loot: dict | None) -> str:
    if not loot:
        return '🎁 <b>Общая добыча</b>\n\nНабор ещё не создан.'
    lines = ['🎁 <b>Общая добыча</b>']
    for item in loot.get('items', []):
        owner = f' → {html.escape(str(item["assigned_name"]))}' if item.get('assigned_name') else ' → не распределено'
        lines.append(f'• <b>{html.escape(str(item["name"]))}</b>{owner}')
    return '\n'.join(lines)


@router.message(Command('find'))
async def search_command(message: Message, db: Database) -> None:
    if await require_character(message, db) is None:
        return
    await message.answer('🔎 Где искать предмет?', reply_markup=search_source_keyboard())


@router.callback_query(F.data == 'assistant:search')
async def search_start(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    if await require_character(callback, db) is None:
        return
    await state.clear()
    await edit_or_answer(callback.message, '🔎 <b>Поиск предмета</b>\n\nГде искать?', reply_markup=search_source_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith('assistant:search_source:'))
async def search_source(callback: CallbackQuery, db: Database) -> None:
    if await require_character(callback, db) is None:
        return
    source = callback.data.rsplit(':', 1)[1]
    await edit_or_answer(callback.message, 'Выбери фильтр:', reply_markup=search_filter_keyboard(source))
    await callback.answer()


@router.callback_query(F.data.startswith('assistant:search_filter:'))
async def search_filter(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    if await require_character(callback, db) is None:
        return
    _, _, source, item_filter = callback.data.split(':')
    await state.set_state(ItemSearchState.query)
    await state.update_data(source=source, item_filter=item_filter)
    await callback.message.answer('Введи часть названия или описания. Чтобы показать всё, отправь <code>*</code>.')
    await callback.answer()


@router.message(ItemSearchState.query)
async def search_query(message: Message, db: Database, state: FSMContext) -> None:
    character = await require_character(message, db)
    if character is None:
        return
    data = await state.get_data()
    source = str(data.get('source') or 'shop')
    rows = await db.search_items_for_player(
        int(character['id']),
        message.text or '',
        str(data.get('item_filter') or 'all'),
        inventory_only=source == 'inventory',
    )
    await state.clear()
    text = 'Ничего не найдено.' if not rows else f'Найдено предметов: <b>{len(rows)}</b>'
    await message.answer(text, reply_markup=search_results_keyboard(rows, source))


@router.callback_query(F.data.startswith('assistant:search_shop_item:'))
async def search_shop_item(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    item = await db.get_item(int(callback.data.rsplit(':', 1)[1]))
    if item is None:
        await callback.answer('Предмет не найден.', show_alert=True)
        return
    can_buy = int(character.get('gold') or 0) >= int(item.get('price') or 0) and int(item.get('shop_quantity', -1)) != 0
    await answer_with_optional_photo(callback.message, item_text(item), item_details_keyboard(int(item['id']), can_buy, 'assistant:search'), item.get('image_file_id'))
    await callback.answer()


@router.callback_query(F.data.startswith('assistant:search_inventory_item:'))
async def search_inventory_item(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    item_id = int(callback.data.rsplit(':', 1)[1])
    item = next((row for row in await db.list_inventory(int(character['id'])) if int(row['id']) == item_id), None)
    if item is None:
        await callback.answer('Предмет уже отсутствует.', show_alert=True)
        return
    await answer_with_optional_photo(
        callback.message,
        item_text(item, int(item['quantity'])),
        inventory_item_keyboard(item_id, can_use=bool(item.get('is_consumable')), can_equip=bool(item.get('equipment_slot')), is_equipped=bool(item.get('is_equipped'))),
        item.get('image_file_id'),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('inventory:use_confirm:'))
async def confirm_consumable(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    item_id = int(callback.data.rsplit(':', 1)[1])
    item = next((row for row in await db.list_inventory(int(character['id'])) if int(row['id']) == item_id), None)
    if item is None or not item.get('is_consumable'):
        await callback.answer('Этот предмет нельзя использовать.', show_alert=True)
        return
    await edit_or_answer(
        callback.message,
        f'Использовать <b>{html.escape(str(item["name"]))}</b> x1? Это уменьшит количество в инвентаре.',
        reply_markup=consumable_confirm_keyboard(item_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('assistant:rsvp:'))
async def rsvp(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    success, text = await db.set_session_attendance(int(character['id']), callback.data.rsplit(':', 1)[1])
    await callback.answer(text, show_alert=not success)


@router.callback_query(F.data == 'assistant:brief')
async def pre_session_brief(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    session = await db.get_session(int(character['session_id'])) if character.get('session_id') else None
    if not session:
        await callback.answer('Сессия не назначена.', show_alert=True)
        return
    status_labels = {'yes': 'буду', 'maybe': 'не уверен', 'no': 'не смогу', 'unknown': 'не отвечал'}
    status = status_labels.get(await db.get_character_attendance(int(character['id'])), 'не отвечал')
    conditions = await db.list_character_condition_details(int(character['id']))
    condition_text = ', '.join(condition_label(row['condition']) for row in conditions) or 'нет'
    carry = await db.get_character_carry_info(int(character['id']))
    equipment = await db.list_equipment(int(character['id']))
    text = (
        format_session_card(session)
        + f'\n\n✅ Ответ: <b>{status}</b>'
        + f'\n❤️ HP: <b>{character["hp"]}/{character["max_hp"]}</b>'
        + f'\n🏷️ Состояния: <b>{html.escape(condition_text)}</b>\n\n'
        + carry_info_text(carry)
        + '\n\n' + equipment_text(equipment)
    )
    await edit_or_answer(callback.message, text, reply_markup=session_card_keyboard())
    await callback.answer()


@router.callback_query(F.data == 'assistant:clues')
async def player_clues(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    if not character.get('session_id'):
        await callback.answer('Сессия не назначена.', show_alert=True)
        return
    await edit_or_answer(callback.message, clues_text(await db.list_campaign_clues(int(character['session_id']))), reply_markup=session_card_keyboard())
    await callback.answer()


@router.callback_query(F.data == 'assistant:loot_player')
async def player_loot(callback: CallbackQuery, db: Database) -> None:
    character = await require_character(callback, db)
    if character is None:
        return
    loot = await db.get_active_group_loot(int(character['session_id'])) if character.get('session_id') else None
    await edit_or_answer(callback.message, loot_text(loot), reply_markup=session_card_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith('assistant:attendance_admin:'))
async def attendance_admin(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not await require_admin(callback, settings):
        return
    session_id = int(callback.data.rsplit(':', 1)[1])
    labels = {'yes': '✅ Будет', 'maybe': '❔ Не уверен', 'no': '❌ Не сможет', 'unknown': '▫️ Не ответил'}
    rows = await db.get_session_attendance(session_id)
    lines = ['✅ <b>Участие в сессии</b>'] + [f'{labels.get(row["status"], "▫️")}: {html.escape(row["display_name"])}' for row in rows]
    await edit_or_answer(callback.message, '\n'.join(lines), reply_markup=session_card_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith('assistant:clues_admin:'))
async def clues_admin(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not await require_admin(callback, settings):
        return
    session_id = int(callback.data.rsplit(':', 1)[1])
    clues = await db.list_campaign_clues(session_id)
    await edit_or_answer(callback.message, clues_text(clues), reply_markup=clues_admin_keyboard(session_id, clues))
    await callback.answer()


@router.callback_query(F.data.startswith('assistant:clue_add:'))
async def clue_add(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if not await require_admin(callback, settings):
        return
    await state.set_state(CampaignClueState.title)
    await state.update_data(session_id=int(callback.data.rsplit(':', 1)[1]))
    await callback.message.answer('Короткое название зацепки:')
    await callback.answer()


@router.message(CampaignClueState.title)
async def clue_title(message: Message, state: FSMContext, settings: Settings) -> None:
    if not await require_admin(message, settings):
        return
    await state.update_data(title=(message.text or '').strip())
    await state.set_state(CampaignClueState.details)
    await message.answer('Добавь пояснение или отправь <code>-</code>:')


@router.message(CampaignClueState.details)
async def clue_details(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if not await require_admin(message, settings):
        return
    data = await state.get_data()
    details = '' if (message.text or '').strip() == '-' else (message.text or '').strip()
    success, result = await db.add_campaign_clue(int(data['session_id']), str(data.get('title') or ''), details)
    await state.clear()
    clues = await db.list_campaign_clues(int(data['session_id']))
    await message.answer(result, reply_markup=clues_admin_keyboard(int(data['session_id']), clues))


@router.callback_query(F.data.startswith('assistant:clue_delete:'))
async def clue_delete(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not await require_admin(callback, settings):
        return
    _, _, session_id_raw, clue_id_raw = callback.data.split(':')
    await db.delete_campaign_clue(int(clue_id_raw))
    clues = await db.list_campaign_clues(int(session_id_raw))
    await edit_or_answer(callback.message, clues_text(clues), reply_markup=clues_admin_keyboard(int(session_id_raw), clues))
    await callback.answer('Удалено')


@router.callback_query(F.data.startswith('assistant:loot_admin:'))
async def loot_admin(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not await require_admin(callback, settings):
        return
    session_id = int(callback.data.rsplit(':', 1)[1])
    loot = await db.get_active_group_loot(session_id)
    await edit_or_answer(callback.message, loot_text(loot), reply_markup=group_loot_admin_keyboard(session_id, loot))
    await callback.answer()


@router.callback_query(F.data.startswith('assistant:loot_generate:'))
async def loot_generate(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not await require_admin(callback, settings):
        return
    session_id = int(callback.data.rsplit(':', 1)[1])
    success, result, _ = await db.create_group_loot(session_id)
    loot = await db.get_active_group_loot(session_id)
    await edit_or_answer(callback.message, result + '\n\n' + loot_text(loot), reply_markup=group_loot_admin_keyboard(session_id, loot))
    await callback.answer('Готово' if success else result, show_alert=not success)


@router.callback_query(F.data.startswith('assistant:loot_choose:'))
async def loot_choose(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not await require_admin(callback, settings):
        return
    _, _, session_id_raw, loot_item_id_raw = callback.data.split(':')
    characters = await db.list_characters(int(session_id_raw))
    await edit_or_answer(callback.message, 'Кому передать предмет?', reply_markup=group_loot_characters_keyboard(int(session_id_raw), int(loot_item_id_raw), characters))
    await callback.answer()


@router.callback_query(F.data.startswith('assistant:loot_assign:'))
async def loot_assign(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not await require_admin(callback, settings):
        return
    _, _, session_id_raw, loot_item_id_raw, character_id_raw = callback.data.split(':')
    success, result = await db.assign_group_loot_item(int(loot_item_id_raw), int(character_id_raw), callback.from_user.id)
    loot = await db.get_active_group_loot(int(session_id_raw))
    await edit_or_answer(callback.message, result + '\n\n' + loot_text(loot), reply_markup=group_loot_admin_keyboard(int(session_id_raw), loot))
    await callback.answer('Передано' if success else result, show_alert=not success)


@router.callback_query(F.data.startswith('assistant:death:'))
async def death_saves(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not await require_admin(callback, settings):
        return
    character_id = int(callback.data.rsplit(':', 1)[1])
    character = await db.get_character(character_id)
    if not character:
        await callback.answer('Персонаж не найден.', show_alert=True)
        return
    text = f'☠️ <b>{html.escape(character["display_name"])}</b>\nУспехи: {character.get("death_save_successes", 0)}/3\nПровалы: {character.get("death_save_failures", 0)}/3'
    await edit_or_answer(callback.message, text, reply_markup=death_saves_keyboard(character_id))
    await callback.answer()


@router.callback_query(F.data.startswith('assistant:death_update:'))
async def death_update(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not await require_admin(callback, settings):
        return
    _, _, character_id_raw, result_type = callback.data.split(':')
    success, result = await db.update_death_save(int(character_id_raw), result_type)
    character = await db.get_character(int(character_id_raw))
    text = result if character else 'Персонаж не найден.'
    await edit_or_answer(callback.message, text, reply_markup=death_saves_keyboard(int(character_id_raw)))
    await callback.answer('Записано' if success else result, show_alert=not success)


@router.callback_query(F.data.startswith('assistant:condition_duration:'))
async def condition_duration(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not await require_admin(callback, settings):
        return
    _, _, character_id_raw, condition, kind, remaining_raw = callback.data.split(':')
    success, result = await db.set_condition_duration(int(character_id_raw), condition, kind, int(remaining_raw))
    await callback.answer(result, show_alert=not success)
    if success:
        await edit_or_answer(callback.message, f'Состояние <b>{condition_label(condition)}</b>: длительность сохранена.', reply_markup=back_to_main_menu())


@router.callback_query(F.data == 'assistant:operations')
async def operations(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not await require_admin(callback, settings):
        return
    rows = await db.list_recent_admin_transactions()
    lines = ['↩️ <b>Последние операции мастера</b>']
    for row in rows:
        status = ' (отменена)' if row.get('reverted_at') else ''
        item = f', {row["item_name"]}' if row.get('item_name') else ''
        lines.append(f'#{row["id"]} {row.get("type")}: {row.get("display_name") or "-"}, {row.get("amount") or 0}{item}{status}')
    await edit_or_answer(callback.message, '\n'.join(lines), reply_markup=operations_keyboard(rows))
    await callback.answer()


@router.callback_query(F.data.startswith('assistant:undo_ask:'))
async def undo_ask(callback: CallbackQuery, settings: Settings) -> None:
    if not await require_admin(callback, settings):
        return
    transaction_id = int(callback.data.rsplit(':', 1)[1])
    await edit_or_answer(callback.message, f'Точно отменить операцию <b>#{transaction_id}</b>?', reply_markup=undo_confirm_keyboard(transaction_id))
    await callback.answer()


@router.callback_query(F.data.startswith('assistant:undo_confirm:'))
async def undo_confirm(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not await require_admin(callback, settings):
        return
    success, result = await db.undo_admin_transaction(int(callback.data.rsplit(':', 1)[1]), callback.from_user.id)
    await edit_or_answer(callback.message, result, reply_markup=back_to_main_menu())
    await callback.answer('Отменено' if success else result, show_alert=not success)
