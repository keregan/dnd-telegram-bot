from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.database import Database, default_sell_price
from app.handlers.common import is_admin
from app.item_rules import equipment_slot_label
from app.keyboards import (
    PAGE_SIZE,
    QUICK_REWARD_PRESETS,
    admin_categories_keyboard,
    admin_characters_keyboard,
    admin_character_manage_keyboard,
    admin_delete_character_confirm_keyboard,
    admin_category_details_keyboard,
    admin_delete_item_confirm_keyboard,
    admin_item_manage_keyboard,
    admin_items_page_keyboard,
    admin_menu,
    back_to_admin_menu,
    categories_keyboard,
    category_label,
    characters_keyboard,
    character_session_select_keyboard,
    give_items_page_keyboard,
    item_availability_keyboard,
    item_category_keyboard,
    item_equipment_slot_keyboard,
    items_keyboard,
    notify_sessions_keyboard,
    quest_award_characters_keyboard,
    quest_details_keyboard,
    quest_item_reward_keyboard,
    quick_reward_presets_keyboard,
    quick_reward_sessions_keyboard,
    quests_keyboard,
    quests_menu_keyboard,
    random_loot_confirm_keyboard,
    rarity_keyboard,
    sessions_keyboard,
    session_details_keyboard,
    assign_character_keyboard,
    session_select_keyboard,
    session_assign_characters_keyboard,
    stock_label,
)
from app.levels import level_progress_text
from app.states import (
    AdminNumberState,
    CreateCategoryState,
    CreateCharacterState,
    CreateItemState,
    CreateQuestState,
    CreateSessionState,
    EditItemState,
    EditCharacterState,
    GiveItemState,
    SetItemLootChanceState,
    SetItemStockState,
    SessionNotifyState,
)
from app.ui import answer_with_optional_photo, edit_or_answer

router = Router(name='admin')


def character_short(character: dict) -> str:
    tg = 'привязан' if character.get('telegram_id') else 'не привязан'
    return (
        f'<b>{character["display_name"]}</b>\n'
        f'Логин: <code>{character["login"]}</code>\n'
        f'{level_progress_text(character)}\n'
        f'Монеты: <b>{character["gold"]}</b> 🪙\n'
        f'Telegram: {tg}'
    )


def item_admin_text(item: dict) -> str:
    status = 'в магазине' if item.get('is_active') else 'только выдача / продажа игроком'
    price = int(item.get('price') or 0)
    sell_price = int(item.get('sell_price') or 0) or default_sell_price(price)
    carry_bonus = float(item.get('carry_bonus_kg') or 0)
    speed_penalty = int(item.get('speed_penalty') or 0)
    carry_line = f'Бонус переносимого веса: <b>+{carry_bonus:.1f}</b> кг\n' if carry_bonus > 0 else ''
    speed_line = f'Штраф скорости: <b>-{speed_penalty}</b>\n' if speed_penalty > 0 else ''
    return (
        f'<b>{item["name"]}</b>\n'
        f'ID: <code>{item["id"]}</code>\n'
        f'Статус: <b>{status}</b>\n'
        f'Остаток в магазине: <b>{stock_label(item)}</b>\n'
        f'Категория: <b>{item.get("category_title") or category_label(item.get("category"))}</b>\n'
        f'Редкость: <b>{item["rarity"]}</b>\n'
        f'Расходник: <b>{"да" if item.get("is_consumable") else "нет"}</b>\n'
        f'Слот экипировки: <b>{equipment_slot_label(item.get("equipment_slot"))}</b>\n'
        f'{carry_line}'
        f'{speed_line}'
        f'Вес: <b>{float(item.get("weight_kg") or 0):.2f}</b> кг\n'
        f'Цена покупки: <b>{price}</b> 🪙\n'
        f'Цена продажи: <b>{sell_price}</b> 🪙\n\n'
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


async def character_admin_text(character: dict, db: Database) -> str:
    carry = await db.get_character_carry_info(int(character['id']))
    tg = 'привязан' if character.get('telegram_id') else 'не привязан'
    return (
        f'👤 <b>{character["display_name"]}</b>\n'
        f'ID: <code>{character["id"]}</code>\n'
        f'Логин: <code>{character["login"]}</code>\n'
        f'Сессия: <b>{character.get("session_title") or "Без сессии"}</b>\n'
        f'Telegram: <b>{tg}</b>\n\n'
        f'{level_progress_text(character)}\n'
        f'Монеты: <b>{character["gold"]}</b> 🪙\n\n'
        f'🎒 <b>Вес и перенос</b>\n{carry_info_text(carry)}'
    )


async def deny_if_not_admin(message_or_callback, settings: Settings) -> bool:
    user_id = message_or_callback.from_user.id
    if is_admin(user_id, settings):
        return False
    target = message_or_callback.message if isinstance(message_or_callback, CallbackQuery) else message_or_callback
    await target.answer('Эта команда доступна только администратору.')
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.answer()
    return True


@router.message(Command('admin'))
async def admin_command(message: Message, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    await message.answer('⚙️ <b>Админ-панель</b>', reply_markup=admin_menu())


@router.callback_query(F.data == 'admin:menu')
async def admin_menu_callback(callback: CallbackQuery, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    await edit_or_answer(callback.message, '⚙️ <b>Админ-панель</b>', reply_markup=admin_menu())
    await callback.answer()



@router.callback_query(F.data == 'admin:sessions')
async def admin_sessions(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    sessions = await db.list_sessions()
    text = '🎲 <b>Сессии</b>\n\n' + '\n'.join(
        f'• <b>{session["title"]}</b> — персонажей: <b>{session.get("characters_count", 0)}</b>'
        for session in sessions
    )
    if not sessions:
        text = '🎲 <b>Сессии</b>\n\nПока нет сессий.'
    await edit_or_answer(callback.message, text, reply_markup=sessions_keyboard(sessions))
    await callback.answer()


@router.callback_query(F.data == 'admin:create_session')
async def admin_create_session_start(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    await state.clear()
    await state.set_state(CreateSessionState.title)
    await callback.message.answer('Введи название сессии. Например: <code>Сессия 1 — Война миров</code>')
    await callback.answer()


@router.message(CreateSessionState.title)
async def admin_create_session_title(message: Message, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    title = message.text.strip()
    if len(title) < 2:
        await message.answer('Название слишком короткое. Введи нормальное название сессии:')
        return
    await state.update_data(title=title)
    await state.set_state(CreateSessionState.description)
    await message.answer('Добавь краткое описание сессии или напиши /skip.')


@router.message(CreateSessionState.description, Command('skip'))
async def admin_create_session_skip_description(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    data = await state.get_data()
    try:
        session_id = await db.create_session(data['title'], '')
    except Exception as exc:
        await message.answer(f'Не получилось создать сессию. Возможно, такое название уже есть.\nОшибка: <code>{exc}</code>')
        await state.clear()
        return
    await state.clear()
    session = await db.get_session(session_id)
    await message.answer(f'Сессия создана ✅\n\n<b>{session["title"]}</b>', reply_markup=session_details_keyboard(session_id))


@router.message(CreateSessionState.description)
async def admin_create_session_finish(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    data = await state.get_data()
    try:
        session_id = await db.create_session(data['title'], message.text.strip())
    except Exception as exc:
        await message.answer(f'Не получилось создать сессию. Возможно, такое название уже есть.\nОшибка: <code>{exc}</code>')
        await state.clear()
        return
    await state.clear()
    session = await db.get_session(session_id)
    await message.answer(f'Сессия создана ✅\n\n<b>{session["title"]}</b>', reply_markup=session_details_keyboard(session_id))


@router.callback_query(F.data.startswith('admin:session:'))
async def admin_session_details(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    session_id = int(callback.data.split(':')[2])
    session = await db.get_session(session_id)
    if session is None:
        await callback.answer('Сессия не найдена.', show_alert=True)
        return
    characters = await db.list_characters(session_id=session_id)
    chars_text = '\n'.join(f'• <b>{character["display_name"]}</b> | ур. {character.get("level", 1)} | 🪙 {character["gold"]}' for character in characters)
    if not chars_text:
        chars_text = 'В этой сессии пока нет персонажей.'
    text = (
        f'🎲 <b>{session["title"]}</b>\n'
        f'ID: <code>{session["id"]}</code>\n'
        f'Персонажей: <b>{session.get("characters_count", 0)}</b>\n\n'
        f'{session.get("description") or "Описание не добавлено."}\n\n'
        f'<b>Персонажи:</b>\n{chars_text}'
    )
    await edit_or_answer(callback.message, text, reply_markup=session_details_keyboard(session_id))
    await callback.answer()


@router.callback_query(F.data == 'admin:session_notifications')
async def admin_session_notifications(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    sessions = await db.list_sessions()
    if not sessions:
        await edit_or_answer(callback.message, 'Сначала создай хотя бы одну сессию.', reply_markup=back_to_admin_menu())
        await callback.answer()
        return
    await edit_or_answer(
        callback.message,
        '🔔 <b>Уведомления сессии</b>\n\n'
        'Выбери сессию, потом напиши дату будущей игры и текст сообщения. '
        'Бот отправит уведомление всем игрокам этой сессии, у кого персонаж привязан к Telegram.',
        reply_markup=notify_sessions_keyboard(sessions),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin:notify_session:'))
async def admin_notify_session_start(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    session_id = int(callback.data.split(':')[2])
    session = await db.get_session(session_id)
    if session is None:
        await callback.answer('Сессия не найдена.', show_alert=True)
        return
    await state.clear()
    await state.update_data(session_id=session_id)
    await state.set_state(SessionNotifyState.date_text)
    await callback.message.answer(
        f'🔔 Уведомление для сессии <b>{session["title"]}</b>\n\n'
        'Введи дату и время будущей сессии. Например: <code>12 июля в 19:00</code>'
    )
    await callback.answer()


@router.message(SessionNotifyState.date_text)
async def admin_notify_session_date(message: Message, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    date_text = message.text.strip()
    if len(date_text) < 2:
        await message.answer('Дата слишком короткая. Напиши дату и время будущей сессии ещё раз:')
        return
    await state.update_data(date_text=date_text)
    await state.set_state(SessionNotifyState.message)
    await message.answer('Теперь напиши текст уведомления для игроков. Например: что подготовить, где остановились, что взять с собой.')


@router.message(SessionNotifyState.message)
async def admin_notify_session_finish(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    notify_text = message.text.strip()
    if len(notify_text) < 2:
        await message.answer('Текст слишком короткий. Напиши сообщение для игроков ещё раз:')
        return

    data = await state.get_data()
    session_id = int(data['session_id'])
    session = await db.get_session(session_id)
    if session is None:
        await state.clear()
        await message.answer('Сессия не найдена. Попробуй начать рассылку заново.', reply_markup=back_to_admin_menu())
        return

    recipients = await db.list_session_recipients(session_id)
    if not recipients:
        await state.clear()
        await message.answer(
            'В этой сессии нет игроков с привязанным Telegram-аккаунтом. '
            'Попроси игроков войти в персонажа через /login.',
            reply_markup=session_details_keyboard(session_id),
        )
        return

    safe_session = html.escape(str(session['title']))
    safe_date = html.escape(str(data.get('date_text') or 'Дата не указана'))
    safe_text = html.escape(notify_text)
    outgoing = (
        '🔔 <b>Будущая сессия</b>\n\n'
        f'Сессия: <b>{safe_session}</b>\n'
        f'Когда: <b>{safe_date}</b>\n\n'
        f'{safe_text}'
    )

    sent = 0
    failed = 0
    for recipient in recipients:
        try:
            await message.bot.send_message(int(recipient['telegram_id']), outgoing)
            sent += 1
        except Exception:
            failed += 1

    await state.clear()
    names = ', '.join(recipient['display_name'] for recipient in recipients)
    await message.answer(
        'Уведомление отправлено ✅\n\n'
        f'Сессия: <b>{session["title"]}</b>\n'
        f'Отправлено: <b>{sent}</b>\n'
        f'Не удалось: <b>{failed}</b>\n'
        f'Получатели: {names}',
        reply_markup=session_details_keyboard(session_id),
    )


@router.callback_query(F.data == 'admin:assign_characters')
async def admin_assign_characters(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    characters = await db.list_characters()
    if not characters:
        await edit_or_answer(callback.message, 'Сначала создай персонажей.', reply_markup=back_to_admin_menu())
        await callback.answer()
        return
    await edit_or_answer(callback.message, 'Кого перенести в другую сессию?', reply_markup=assign_character_keyboard(characters, 'admin:sessions'))
    await callback.answer()


@router.callback_query(F.data.startswith('admin:assign_character:'))
async def admin_assign_character_select_session(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    character_id = int(callback.data.split(':')[2])
    character = await db.get_character(character_id)
    if character is None:
        await callback.answer('Персонаж не найден.', show_alert=True)
        return
    sessions = await db.list_sessions(only_active=True)
    await edit_or_answer(
        callback.message,
        f'Выбери сессию для персонажа <b>{character["display_name"]}</b>.\n\nСейчас: <b>{character.get("session_title") or "Без сессии"}</b>',
        reply_markup=session_select_keyboard(sessions, character_id, 'admin:assign_characters'),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin:session_assign:'))
async def admin_session_assign_character(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    session_id = int(callback.data.split(':')[2])
    session = await db.get_session(session_id)
    if session is None:
        await callback.answer('Сессия не найдена.', show_alert=True)
        return
    characters = await db.list_characters()
    await edit_or_answer(
        callback.message,
        f'Кого добавить в сессию <b>{session["title"]}</b>?',
        reply_markup=session_assign_characters_keyboard(session_id, characters),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin:set_character_session:'))
async def admin_set_character_session(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    _, _, character_id_raw, session_id_raw = callback.data.split(':')
    success, result = await db.set_character_session(int(character_id_raw), int(session_id_raw))
    await callback.answer('Готово ✅' if success else result, show_alert=not success)
    session = await db.get_session(int(session_id_raw))
    if session:
        characters = await db.list_characters(session_id=int(session_id_raw))
        chars_text = '\n'.join(f'• <b>{character["display_name"]}</b>' for character in characters) or 'В этой сессии пока нет персонажей.'
        await edit_or_answer(
            callback.message,
            f'{result}\n\n🎲 <b>{session["title"]}</b>\n\n<b>Персонажи:</b>\n{chars_text}',
            reply_markup=session_details_keyboard(int(session_id_raw)),
        )


@router.callback_query(F.data == 'admin:create_character')
async def create_character_start(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    await state.clear()
    await state.set_state(CreateCharacterState.login)
    await callback.message.answer('Введи логин нового персонажа. Например: <code>aragorn</code>')
    await callback.answer()


@router.message(CreateCharacterState.login)
async def create_character_login(message: Message, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    login = message.text.strip()
    if len(login) < 3:
        await message.answer('Логин должен быть минимум 3 символа. Введи другой логин:')
        return
    await state.update_data(login=login)
    await state.set_state(CreateCharacterState.password)
    await message.answer('Введи пароль для персонажа. Потом ты отдашь его игроку.')


@router.message(CreateCharacterState.password)
async def create_character_password(message: Message, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    password = message.text.strip()
    if len(password) < 4:
        await message.answer('Пароль лучше сделать минимум 4 символа. Введи другой пароль:')
        return
    await state.update_data(password=password)
    await state.set_state(CreateCharacterState.display_name)
    await message.answer('Введи имя персонажа, которое будет видно в боте. Например: <code>Арагорн</code>')


@router.message(CreateCharacterState.display_name)
async def create_character_display_name(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    data = await state.get_data()
    display_name = message.text.strip()
    try:
        character_id = await db.create_character(data['login'], data['password'], display_name)
    except Exception as exc:
        await message.answer(f'Не получилось создать персонажа. Возможно, логин уже занят.\nОшибка: <code>{exc}</code>')
        await state.clear()
        return
    await state.clear()
    character = await db.get_character(character_id)
    await message.answer(
        'Персонаж создан ✅\n\n'
        f'ID: <code>{character_id}</code>\n'
        f'Имя: <b>{display_name}</b>\n'
        f'Логин: <code>{data["login"]}</code>\n'
        f'Пароль: <code>{data["password"]}</code>\n\n'
        'Передай логин и пароль игроку. Пароль в базе хранится в виде хэша.',
        reply_markup=admin_character_manage_keyboard(character) if character else back_to_admin_menu(),
    )


@router.callback_query(F.data == 'admin:characters')
async def characters_list(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    characters = await db.list_characters()
    if not characters:
        await edit_or_answer(callback.message, 'Персонажей пока нет.', reply_markup=back_to_admin_menu())
        await callback.answer()
        return
    text = (
        '👥 <b>Персонажи</b>\n\n'
        'Выбери персонажа кнопкой ниже, чтобы открыть карточку и изменить имя, логин, пароль, XP, монеты, Силу, лимит веса или сессию.\n\n'
        + '\n\n'.join(character_short(character) for character in characters)
    )
    await edit_or_answer(callback.message, text, reply_markup=admin_characters_keyboard(characters))
    await callback.answer()


@router.callback_query(F.data.startswith('admin:character:'))
async def admin_character_details(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    character_id = int(callback.data.split(':')[2])
    character = await db.get_character(character_id)
    if character is None:
        await callback.answer('Персонаж не найден.', show_alert=True)
        return
    await edit_or_answer(
        callback.message,
        await character_admin_text(character, db),
        reply_markup=admin_character_manage_keyboard(character),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin:edit_character_session:'))
async def admin_edit_character_session(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    character_id = int(callback.data.split(':')[2])
    character = await db.get_character(character_id)
    if character is None:
        await callback.answer('Персонаж не найден.', show_alert=True)
        return
    sessions = await db.list_sessions(only_active=True)
    await edit_or_answer(
        callback.message,
        f'Выбери новую сессию для персонажа <b>{character["display_name"]}</b>.\n\nСейчас: <b>{character.get("session_title") or "Без сессии"}</b>',
        reply_markup=character_session_select_keyboard(sessions, character_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin:character_session_set:'))
async def admin_character_session_set(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    _, _, character_id_raw, session_id_raw = callback.data.split(':')
    success, result = await db.set_character_session(int(character_id_raw), int(session_id_raw))
    await callback.answer('Готово ✅' if success else result, show_alert=not success)
    character = await db.get_character(int(character_id_raw))
    if character:
        await edit_or_answer(callback.message, await character_admin_text(character, db), reply_markup=admin_character_manage_keyboard(character))


@router.callback_query(F.data.startswith('admin:edit_character:'))
async def admin_edit_character_start(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    _, _, field, character_id_raw = callback.data.split(':')
    character_id = int(character_id_raw)
    character = await db.get_character(character_id)
    if character is None:
        await callback.answer('Персонаж не найден.', show_alert=True)
        return
    labels = {
        'display_name': 'новое имя персонажа',
        'login': 'новый логин',
        'password': 'новый пароль',
        'xp': 'новое количество XP',
        'gold': 'новое количество монет',
        'strength_score': 'значение Силы от 1 до 30',
        'max_carry_kg': 'лимит веса в кг или слово авто',
    }
    await state.clear()
    await state.update_data(character_id=character_id, field=field)
    await state.set_state(EditCharacterState.value)
    await callback.message.answer(
        f'Персонаж: <b>{character["display_name"]}</b>\n'
        f'Введи {labels.get(field, "новое значение")}.\n\n'
        'Для лимита веса можно написать <code>авто</code>, тогда лимит снова будет считаться от Силы.',
    )
    await callback.answer()


@router.message(EditCharacterState.value)
async def admin_edit_character_finish(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    data = await state.get_data()
    character_id = int(data['character_id'])
    field = str(data['field'])
    value = message.text.strip()
    if field == 'password':
        success, result = await db.update_character_password(character_id, value)
    else:
        success, result = await db.update_character_field(character_id, field, value)
    character = await db.get_character(character_id)
    if character is None:
        await state.clear()
        await message.answer('Персонаж не найден.', reply_markup=back_to_admin_menu())
        return
    if not success:
        await state.clear()
        await message.answer(
            f'{result}\n\n'
            'Изменение не применено. Выбери поле ещё раз, если хочешь повторить.',
            reply_markup=admin_character_manage_keyboard(character),
        )
        return
    await state.clear()
    await message.answer(
        f'{result}\n\n' + await character_admin_text(character, db),
        reply_markup=admin_character_manage_keyboard(character),
    )


@router.callback_query(F.data.startswith('admin:delete_character:'))
async def admin_delete_character_start(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    character_id = int(callback.data.split(':')[2])
    character = await db.get_character(character_id)
    if character is None:
        await callback.answer('Персонаж не найден.', show_alert=True)
        return
    await edit_or_answer(
        callback.message,
        f'⚠️ Удалить персонажа <b>{character["display_name"]}</b>?\n\n'
        'Удалится персонаж и весь его инвентарь. Это действие лучше делать только после бэкапа базы.',
        reply_markup=admin_delete_character_confirm_keyboard(character_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin:delete_character_confirm:'))
async def admin_delete_character_confirm(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    character_id = int(callback.data.split(':')[2])
    success, result = await db.delete_character(character_id)
    await callback.answer('Удалено ✅' if success else result, show_alert=not success)
    characters = await db.list_characters()
    await edit_or_answer(
        callback.message,
        result + '\n\n👥 <b>Персонажи</b>',
        reply_markup=admin_characters_keyboard(characters) if characters else back_to_admin_menu(),
    )


@router.callback_query(F.data.in_({'admin:add_xp', 'admin:add_gold'}))
async def select_character_for_number(callback: CallbackQuery, db: Database, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    action = 'xp' if callback.data == 'admin:add_xp' else 'gold'
    characters = await db.list_characters()
    if not characters:
        await edit_or_answer(callback.message, 'Сначала создай хотя бы одного персонажа.', reply_markup=back_to_admin_menu())
        await callback.answer()
        return
    await state.clear()
    await state.update_data(admin_action=action)
    text = 'Кому добавить опыт?' if action == 'xp' else 'Кому добавить монеты?'
    await edit_or_answer(callback.message, text, reply_markup=characters_keyboard(characters, 'admin:number_user'))
    await callback.answer()


@router.callback_query(F.data.startswith('admin:number_user:'))
async def enter_number_amount(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    character_id = int(callback.data.split(':')[2])
    data = await state.get_data()
    action = data.get('admin_action')
    await state.update_data(character_id=character_id)
    await state.set_state(AdminNumberState.amount)
    if action == 'xp':
        await callback.message.answer('Введи количество XP. Можно отрицательное число, если нужно списать опыт.')
    else:
        await callback.message.answer('Введи количество монет. Можно отрицательное число, если нужно списать монеты.')
    await callback.answer()


@router.message(AdminNumberState.amount)
async def add_number_amount(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer('Нужно ввести целое число. Например: <code>50</code> или <code>-10</code>')
        return

    data = await state.get_data()
    character_id = int(data['character_id'])
    action = data['admin_action']
    before = await db.get_character(character_id)
    if action == 'xp':
        await db.add_xp(character_id, amount, message.from_user.id)
        label = 'XP'
    else:
        await db.add_gold(character_id, amount, message.from_user.id)
        label = 'монет'

    character = await db.get_character(character_id)
    level_line = ''
    if action == 'xp' and before:
        if int(before['level']) != int(character['level']):
            level_line = f'Уровень изменился: <b>{before["level"]}</b> → <b>{character["level"]}</b> 🎉\n'
        else:
            level_line = f'Текущий уровень: <b>{character["level"]}</b>\n'
    await state.clear()
    await message.answer(
        f'Готово ✅\n'
        f'{character["display_name"]}: {label} изменены на <b>{amount}</b>.\n'
        f'{level_line}'
        f'Текущий XP: <b>{character["xp"]}</b>\n'
        f'До следующего уровня: <b>{character["xp_to_next_level"]}</b> XP\n'
        f'Бонус владения: <b>+{character["proficiency_bonus"]}</b>\n'
        f'Текущие монеты: <b>{character["gold"]}</b> 🪙',
        reply_markup=back_to_admin_menu(),
    )



@router.callback_query(F.data == 'admin:categories')
async def admin_categories(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    categories = await db.list_categories()
    text = '📂 <b>Категории предметов</b>\n\n' + '\n'.join(
        f'• <b>{category["title"]}</b> — <code>{category["value"]}</code>'
        for category in categories
    )
    await edit_or_answer(callback.message, text, reply_markup=admin_categories_keyboard(categories))
    await callback.answer()


@router.callback_query(F.data == 'admin:create_category')
async def admin_create_category_start(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    await state.clear()
    await state.set_state(CreateCategoryState.name)
    await callback.message.answer('Введи название новой категории. Например: <code>🧿 Артефакты</code>')
    await callback.answer()


@router.message(CreateCategoryState.name)
async def admin_create_category_finish(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    try:
        category = await db.create_category(message.text.strip())
    except ValueError as exc:
        await message.answer(str(exc) + '\nВведи другое название:')
        return
    await state.clear()
    categories = await db.list_categories()
    await message.answer(
        f'Категория создана ✅\n\n<b>{category["title"]}</b>\nКод: <code>{category["value"]}</code>\n\n'
        'Теперь её можно выбрать при создании или редактировании предмета.',
        reply_markup=admin_categories_keyboard(categories),
    )


@router.callback_query(F.data.startswith('admin:category:'))
async def admin_category_details(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    value = callback.data.split(':', 2)[2]
    category = await db.get_category(value)
    if category is None:
        await callback.answer('Категория не найдена.', show_alert=True)
        return
    items_count = await db.count_items(only_active=False, category=value)
    await edit_or_answer(
        callback.message,
        f'📂 <b>{category["title"]}</b>\n'
        f'Код: <code>{category["value"]}</code>\n'
        f'Предметов внутри: <b>{items_count}</b>\n\n'
        'Удалять можно только пустые пользовательские категории. Стандартные категории защищены.',
        reply_markup=admin_category_details_keyboard(value),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin:delete_category:'))
async def admin_delete_category(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    value = callback.data.split(':', 2)[2]
    success, result = await db.delete_category(value)
    await callback.answer(result, show_alert=not success)
    categories = await db.list_categories()
    await edit_or_answer(callback.message, '📂 <b>Категории предметов</b>\n\n' + result, reply_markup=admin_categories_keyboard(categories))


@router.callback_query(F.data == 'admin:auto_categorize_items')
async def admin_auto_categorize_items(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    result = await db.auto_categorize_items()
    categories = await db.list_categories()
    changed = int(result.get('changed', 0))
    by_category = result.get('by_category', {})

    if changed <= 0:
        text = (
            '🧭 <b>Распределение предметов</b>\n\n'
            'Готово. Предметы уже разложены по категориям, новых изменений нет.'
        )
    else:
        lines = []
        for value, count in sorted(by_category.items(), key=lambda item: str(item[0])):
            category = await db.get_category(str(value))
            title = category['title'] if category else str(value)
            lines.append(f'• <b>{title}</b>: {count}')
        text = (
            '🧭 <b>Распределение предметов</b>\n\n'
            f'Обновлено предметов: <b>{changed}</b>\n\n'
            + '\n'.join(lines)
        )

    await edit_or_answer(callback.message, text, reply_markup=admin_categories_keyboard(categories))
    await callback.answer('Готово ✅')


@router.callback_query(F.data == 'admin:create_item')
async def create_item_start(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    await state.clear()
    await state.set_state(CreateItemState.name)
    await callback.message.answer('Введи название предмета. Например: <code>Верёвка 15 метров</code>')
    await callback.answer()


@router.message(CreateItemState.name)
async def create_item_name(message: Message, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(CreateItemState.description)
    await message.answer('Введи описание предмета. Например: бонусы, свойства, ограничения.')


@router.message(CreateItemState.description)
async def create_item_description(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    await state.update_data(description=message.text.strip())
    await state.set_state(CreateItemState.category)
    categories = await db.list_categories()
    await message.answer('Выбери категорию предмета:', reply_markup=item_category_keyboard('item_category', 'admin:menu', categories))


@router.callback_query(CreateItemState.category, F.data.startswith('item_category:'))
async def create_item_category(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    category = callback.data.split(':', 1)[1]
    await state.update_data(category=category)
    await state.set_state(CreateItemState.price)
    await callback.message.answer('Введи цену покупки в монетах. Цена продажи автоматически станет на 20% ниже. Например: <code>10</code>')
    await callback.answer()


@router.message(CreateItemState.price)
async def create_item_price(message: Message, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    try:
        price = int(message.text.strip())
    except ValueError:
        await message.answer('Цена должна быть целым числом. Например: <code>10</code>')
        return
    if price < 0:
        await message.answer('Цена не может быть отрицательной. Введи цену ещё раз:')
        return
    await state.update_data(price=price)
    await state.set_state(CreateItemState.rarity)
    await message.answer('Выбери редкость предмета:', reply_markup=rarity_keyboard())


@router.callback_query(CreateItemState.rarity, F.data.startswith('rarity:'))
async def create_item_rarity(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    rarity = callback.data.split(':')[1]
    await state.update_data(rarity=rarity)
    await state.set_state(CreateItemState.loot_chance)
    await callback.message.answer(
        'Введи шанс выпадения предмета при рандомном луте от 0 до 100.\n\n'
        '<code>0</code> — не выпадает случайно\n'
        '<code>25</code> — шанс 25% при броске лута\n'
        '<code>100</code> — выпадет всегда'
    )
    await callback.answer()


@router.message(CreateItemState.loot_chance)
async def create_item_loot_chance(message: Message, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    try:
        chance = int(message.text.strip())
    except ValueError:
        await message.answer('Нужно ввести число от 0 до 100. Например: <code>25</code>')
        return
    if chance < 0 or chance > 100:
        await message.answer('Шанс должен быть от 0 до 100. Введи ещё раз:')
        return
    await state.update_data(loot_chance_percent=chance)
    await state.set_state(CreateItemState.availability)
    await message.answer(
        'Добавить предмет в магазин или оставить только для выдачи игрокам?',
        reply_markup=item_availability_keyboard(),
    )


@router.callback_query(CreateItemState.availability, F.data.startswith('item_availability:'))
async def create_item_availability(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    mode = callback.data.split(':')[1]
    if mode == 'shop':
        await state.update_data(is_active=True)
        await state.set_state(CreateItemState.shop_quantity)
        await callback.message.answer(
            'Введи остаток в магазине.\n\n'
            '<code>-1</code> — без лимита\n'
            '<code>0</code> — временно нет в наличии\n'
            '<code>5</code> — можно купить только 5 штук'
        )
    else:
        await state.update_data(is_active=False, shop_quantity=0)
        await state.set_state(CreateItemState.photo)
        await callback.message.answer('Предмет будет только для выдачи игрокам. Отправь картинку предмета одним фото. Если картинка не нужна — напиши /skip')
    await callback.answer()


@router.message(CreateItemState.shop_quantity)
async def create_item_shop_quantity(message: Message, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    try:
        shop_quantity = int(message.text.strip())
    except ValueError:
        await message.answer('Нужно ввести целое число: <code>-1</code>, <code>0</code>, <code>5</code> и т.д.')
        return
    if shop_quantity < -1:
        await message.answer('Минимальное значение — <code>-1</code>. Введи остаток ещё раз:')
        return
    await state.update_data(shop_quantity=shop_quantity)
    await state.set_state(CreateItemState.photo)
    await message.answer('Отправь картинку предмета одним фото. Если картинка не нужна — напиши /skip')


@router.message(CreateItemState.photo, Command('skip'))
async def create_item_skip_photo(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    await finish_item_creation(message, state, db, image_file_id=None)


@router.message(CreateItemState.photo, F.photo)
async def create_item_photo(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    image_file_id = message.photo[-1].file_id
    await finish_item_creation(message, state, db, image_file_id=image_file_id)


@router.message(CreateItemState.photo)
async def create_item_photo_wrong(message: Message) -> None:
    await message.answer('Нужно отправить картинку как фото или написать /skip.')


async def finish_item_creation(message: Message, state: FSMContext, db: Database, image_file_id: str | None) -> None:
    data = await state.get_data()
    item_id = await db.create_item(
        name=data['name'],
        description=data['description'],
        price=int(data['price']),
        rarity=data['rarity'],
        category=data.get('category', 'other'),
        image_file_id=image_file_id,
        is_active=bool(data.get('is_active', True)),
        shop_quantity=int(data.get('shop_quantity', -1)),
        loot_chance_percent=int(data.get('loot_chance_percent', 0)),
    )
    item = await db.get_item(item_id)
    await message.answer(
        'Предмет создан ✅\n\n' + item_admin_text(item),
        reply_markup=back_to_admin_menu(),
    )
    await state.clear()


async def render_admin_items_page(message: Message, db: Database, page: int = 0) -> None:
    total_items = await db.count_items(only_active=False)
    if total_items <= 0:
        await edit_or_answer(message, 'Предметов пока нет.', reply_markup=back_to_admin_menu())
        return
    total_pages = max(1, (total_items + PAGE_SIZE - 1) // PAGE_SIZE)
    safe_page = min(max(0, int(page)), total_pages - 1)
    items = await db.list_items(only_active=False, limit=PAGE_SIZE, offset=safe_page * PAGE_SIZE)
    lines = []
    for item in items:
        category_title = item.get('category_title') or category_label(item.get('category'))
        sell_price = int(item.get('sell_price') or 0) or default_sell_price(int(item.get('price') or 0))
        carry_part = ''
        if float(item.get('carry_bonus_kg') or 0) > 0:
            carry_part = f', +{float(item.get("carry_bonus_kg") or 0):.1f} кг'
        if int(item.get('speed_penalty') or 0) > 0:
            carry_part += f', -{int(item.get("speed_penalty") or 0)} скорости'
        lines.append(
            f'• #{item["id"]} {"✅" if item["is_active"] else "🚫"} {category_title} | <b>{item["name"]}</b> — '
            f'покупка {item["price"]} 🪙 / продажа {sell_price} 🪙, {item["rarity"]}{carry_part}, '
            f'остаток: {stock_label(item)}, лут: {item.get("loot_chance_percent", 0)}%'
        )
    text = (
        '📦 <b>Все предметы</b>\n'
        f'Страница: <b>{safe_page + 1}/{total_pages}</b>\n'
        f'Всего предметов: <b>{total_items}</b>\n\n'
        + '\n'.join(lines)
    )
    await edit_or_answer(message, text, reply_markup=admin_items_page_keyboard(items, safe_page, total_pages))


@router.callback_query(F.data == 'admin:items')
async def admin_items(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    await render_admin_items_page(callback.message, db, 0)
    await callback.answer()


@router.callback_query(F.data.startswith('admin:items_page:'))
async def admin_items_page(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    page = int(callback.data.split(':')[2])
    await render_admin_items_page(callback.message, db, page)
    await callback.answer()


@router.callback_query(F.data.startswith('admin:item:'))
async def admin_item_details(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    item_id = int(callback.data.split(':')[2])
    item = await db.get_item(item_id)
    if item is None:
        await callback.answer('Предмет не найден.', show_alert=True)
        return
    text = item_admin_text(item)
    await answer_with_optional_photo(
        callback.message,
        text,
        reply_markup=admin_item_manage_keyboard(item),
        image_ref=item.get('image_file_id'),
    )
    await callback.answer()



EDIT_FIELD_LABELS = {
    'name': 'название',
    'description': 'описание / свойства',
    'price': 'цену покупки',
    'sell_price': 'цену продажи',
    'weight_kg': 'вес в кг',
    'carry_bonus_kg': 'бонус переносимого веса в кг',
    'speed_penalty': 'штраф скорости',
}


@router.callback_query(F.data.startswith('admin:edit_item:'))
async def admin_edit_item_start(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    _, _, field, item_id_raw = callback.data.split(':')
    if field not in EDIT_FIELD_LABELS:
        await callback.answer('Это поле нельзя изменить через эту кнопку.', show_alert=True)
        return
    item_id = int(item_id_raw)
    item = await db.get_item(item_id)
    if item is None:
        await callback.answer('Предмет не найден.', show_alert=True)
        return
    await state.clear()
    await state.update_data(item_id=item_id, edit_field=field)
    await state.set_state(EditItemState.value)
    await callback.message.answer(f'Введи новое значение для поля <b>{EDIT_FIELD_LABELS[field]}</b> предмета <b>{item["name"]}</b>:')
    await callback.answer()


@router.message(EditItemState.value)
async def admin_edit_item_value_finish(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    data = await state.get_data()
    item_id = int(data['item_id'])
    field = data['edit_field']
    value = message.text.strip()
    if field == 'name' and len(value) < 2:
        await message.answer('Название слишком короткое. Введи новое название ещё раз:')
        return
    if field in {'price', 'sell_price'}:
        try:
            value = int(value)
        except ValueError:
            await message.answer('Цена должна быть целым числом. Например: <code>10</code>')
            return
        if value < 0:
            await message.answer('Цена не может быть отрицательной. Введи цену ещё раз:')
            return
    if field in {'weight_kg', 'carry_bonus_kg'}:
        try:
            value = float(value.replace(',', '.'))
        except ValueError:
            await message.answer('Значение должно быть числом в кг. Например: <code>1.5</code>')
            return
        if value < 0:
            await message.answer('Значение не может быть отрицательным. Введи число ещё раз:')
            return
    if field == 'speed_penalty':
        try:
            value = int(value)
        except ValueError:
            await message.answer('Штраф скорости должен быть целым числом. Например: <code>10</code>')
            return
        if value < 0:
            await message.answer('Штраф скорости не может быть отрицательным. Введи число ещё раз:')
            return
    await db.update_item_field(item_id, field, value)
    item = await db.get_item(item_id)
    await state.clear()
    await message.answer('Предмет обновлён ✅\n\n' + item_admin_text(item), reply_markup=admin_item_manage_keyboard(item))


@router.callback_query(F.data.startswith('admin:edit_item_rarity:'))
async def admin_edit_item_rarity_start(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    item_id = int(callback.data.split(':')[2])
    item = await db.get_item(item_id)
    if item is None:
        await callback.answer('Предмет не найден.', show_alert=True)
        return
    await state.clear()
    await state.update_data(item_id=item_id, edit_field='rarity')
    await state.set_state(EditItemState.value)
    await callback.message.answer(f'Выбери новую редкость для предмета <b>{item["name"]}</b>:', reply_markup=rarity_keyboard())
    await callback.answer()


@router.callback_query(EditItemState.value, F.data.startswith('rarity:'))
async def admin_edit_item_rarity_finish(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    data = await state.get_data()
    if data.get('edit_field') != 'rarity':
        return
    item_id = int(data['item_id'])
    rarity = callback.data.split(':', 1)[1]
    await db.update_item_field(item_id, 'rarity', rarity)
    item = await db.get_item(item_id)
    await state.clear()
    await callback.message.answer('Редкость обновлена ✅\n\n' + item_admin_text(item), reply_markup=admin_item_manage_keyboard(item))
    await callback.answer()


@router.callback_query(F.data.startswith('admin:edit_item_category:'))
async def admin_edit_item_category_start(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    item_id = int(callback.data.split(':')[2])
    item = await db.get_item(item_id)
    if item is None:
        await callback.answer('Предмет не найден.', show_alert=True)
        return
    await state.clear()
    await state.update_data(item_id=item_id, edit_field='category')
    await state.set_state(EditItemState.value)
    categories = await db.list_categories()
    await callback.message.answer(f'Выбери новую категорию для предмета <b>{item["name"]}</b>:', reply_markup=item_category_keyboard('edit_category', f'admin:item:{item_id}', categories))
    await callback.answer()


@router.callback_query(EditItemState.value, F.data.startswith('edit_category:'))
async def admin_edit_item_category_finish(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    data = await state.get_data()
    if data.get('edit_field') != 'category':
        return
    item_id = int(data['item_id'])
    category = callback.data.split(':', 1)[1]
    await db.update_item_field(item_id, 'category', category)
    item = await db.get_item(item_id)
    await state.clear()
    await callback.message.answer('Категория обновлена ✅\n\n' + item_admin_text(item), reply_markup=admin_item_manage_keyboard(item))
    await callback.answer()


@router.callback_query(F.data.startswith('admin:edit_item_photo:'))
async def admin_edit_item_photo_start(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    item_id = int(callback.data.split(':')[2])
    item = await db.get_item(item_id)
    if item is None:
        await callback.answer('Предмет не найден.', show_alert=True)
        return
    await state.clear()
    await state.update_data(item_id=item_id)
    await state.set_state(EditItemState.photo)
    await callback.message.answer('Отправь новую картинку одним фото. Если нужно убрать картинку — напиши /skip')
    await callback.answer()


@router.message(EditItemState.photo, Command('skip'))
async def admin_edit_item_photo_clear(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    data = await state.get_data()
    item_id = int(data['item_id'])
    await db.update_item_field(item_id, 'image_file_id', None)
    item = await db.get_item(item_id)
    await state.clear()
    await message.answer('Картинка удалена ✅\n\n' + item_admin_text(item), reply_markup=admin_item_manage_keyboard(item))


@router.message(EditItemState.photo, F.photo)
async def admin_edit_item_photo_finish(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    data = await state.get_data()
    item_id = int(data['item_id'])
    image_file_id = message.photo[-1].file_id
    await db.update_item_field(item_id, 'image_file_id', image_file_id)
    item = await db.get_item(item_id)
    await state.clear()
    await message.answer('Картинка обновлена ✅\n\n' + item_admin_text(item), reply_markup=admin_item_manage_keyboard(item))


@router.message(EditItemState.photo)
async def admin_edit_item_photo_wrong(message: Message) -> None:
    await message.answer('Нужно отправить картинку как фото или написать /skip.')


@router.callback_query(F.data.startswith('admin:delete_item:'))
async def admin_delete_item_start(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    item_id = int(callback.data.split(':')[2])
    item = await db.get_item(item_id)
    if item is None:
        await callback.answer('Предмет не найден.', show_alert=True)
        return
    await callback.message.answer(
        f'Удалить предмет <b>{item["name"]}</b>?\n\n'
        'Важно: предмет исчезнет из магазина и инвентарей игроков. Если он был наградой квеста, связь с квестом будет очищена.',
        reply_markup=admin_delete_item_confirm_keyboard(item_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin:delete_item_confirm:'))
async def admin_delete_item_finish(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    item_id = int(callback.data.split(':')[2])
    item = await db.get_item(item_id)
    if item is None:
        await callback.answer('Предмет уже удалён.', show_alert=True)
        return
    await db.delete_item(item_id)
    await callback.message.answer(f'Предмет <b>{item["name"]}</b> удалён ✅', reply_markup=back_to_admin_menu())
    await callback.answer()


@router.callback_query(F.data.startswith('admin:toggle_item:'))
async def admin_toggle_item(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    item_id = int(callback.data.split(':')[2])
    item = await db.get_item(item_id)
    if item is None:
        await callback.answer('Предмет не найден.', show_alert=True)
        return
    new_active = not bool(item['is_active'])
    await db.update_item_active(item_id, new_active)
    await callback.answer('Статус предмета обновлён ✅')
    updated = await db.get_item(item_id)
    await callback.message.answer(item_admin_text(updated), reply_markup=admin_item_manage_keyboard(updated))


@router.callback_query(F.data.startswith('admin:toggle_consumable:'))
async def admin_toggle_consumable(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    item_id = int(callback.data.split(':')[2])
    item = await db.get_item(item_id)
    if item is None:
        await callback.answer('Предмет не найден.', show_alert=True)
        return
    await db.update_item_consumable(item_id, not bool(item.get('is_consumable')))
    updated = await db.get_item(item_id)
    await callback.answer('Тип предмета обновлён ✅')
    await callback.message.answer(item_admin_text(updated), reply_markup=admin_item_manage_keyboard(updated))


@router.callback_query(F.data.startswith('admin:equipment_slot:'))
async def admin_equipment_slot_start(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    item_id = int(callback.data.split(':')[2])
    item = await db.get_item(item_id)
    if item is None:
        await callback.answer('Предмет не найден.', show_alert=True)
        return
    await callback.message.answer(
        f'Выбери слот экипировки для предмета <b>{item["name"]}</b>.\n\n'
        'Если выбрать «Не экипируется», предмет пропадёт из экипировки у всех персонажей.',
        reply_markup=item_equipment_slot_keyboard(item_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin:set_equipment_slot:'))
async def admin_equipment_slot_finish(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    _, _, item_id_raw, slot = callback.data.split(':')
    item_id = int(item_id_raw)
    await db.update_item_equipment_slot(item_id, '' if slot == 'none' else slot)
    item = await db.get_item(item_id)
    if item is None:
        await callback.answer('Предмет не найден.', show_alert=True)
        return
    await callback.answer('Слот экипировки обновлён ✅')
    await callback.message.answer(item_admin_text(item), reply_markup=admin_item_manage_keyboard(item))


@router.callback_query(F.data.startswith('admin:set_stock:'))
async def admin_set_stock_start(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    item_id = int(callback.data.split(':')[2])
    item = await db.get_item(item_id)
    if item is None:
        await callback.answer('Предмет не найден.', show_alert=True)
        return
    await state.clear()
    await state.update_data(item_id=item_id)
    await state.set_state(SetItemStockState.quantity)
    await callback.message.answer(
        f'Введи новый остаток для предмета <b>{item["name"]}</b>.\n\n'
        '<code>-1</code> — без лимита\n'
        '<code>0</code> — закончился\n'
        '<code>5</code> — осталось 5 штук'
    )
    await callback.answer()


@router.message(SetItemStockState.quantity)
async def admin_set_stock_finish(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    try:
        quantity = int(message.text.strip())
    except ValueError:
        await message.answer('Нужно ввести целое число: <code>-1</code>, <code>0</code>, <code>5</code> и т.д.')
        return
    if quantity < -1:
        await message.answer('Минимальное значение — <code>-1</code>. Введи остаток ещё раз:')
        return
    data = await state.get_data()
    item_id = int(data['item_id'])
    await db.update_item_stock(item_id, quantity)
    item = await db.get_item(item_id)
    await state.clear()
    await message.answer('Остаток обновлён ✅\n\n' + item_admin_text(item), reply_markup=admin_item_manage_keyboard(item))


@router.callback_query(F.data.startswith('admin:set_loot_chance:'))
async def admin_set_loot_chance_start(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    item_id = int(callback.data.split(':')[2])
    item = await db.get_item(item_id)
    if item is None:
        await callback.answer('Предмет не найден.', show_alert=True)
        return
    await state.clear()
    await state.update_data(item_id=item_id)
    await state.set_state(SetItemLootChanceState.chance)
    await callback.message.answer(
        f'Введи шанс выпадения для предмета <b>{item["name"]}</b> от 0 до 100.\n\n'
        '<code>0</code> — не участвует в рандомном луте\n'
        '<code>25</code> — шанс 25%\n'
        '<code>100</code> — выпадет всегда'
    )
    await callback.answer()


@router.message(SetItemLootChanceState.chance)
async def admin_set_loot_chance_finish(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    try:
        chance = int(message.text.strip())
    except ValueError:
        await message.answer('Нужно ввести целое число от 0 до 100. Например: <code>25</code>')
        return
    if chance < 0 or chance > 100:
        await message.answer('Шанс должен быть от 0 до 100. Введи ещё раз:')
        return
    data = await state.get_data()
    item_id = int(data['item_id'])
    await db.update_item_loot_chance(item_id, chance)
    item = await db.get_item(item_id)
    await state.clear()
    await message.answer('Шанс лута обновлён ✅\n\n' + item_admin_text(item), reply_markup=admin_item_manage_keyboard(item))


def quest_text(quest: dict) -> str:
    item_line = 'Предмет: <b>нет</b>'
    if quest.get('item_id') and int(quest.get('item_quantity', 0)) > 0:
        item_line = f'Предмет: <b>{quest.get("item_name") or "предмет"}</b> ×{quest["item_quantity"]}'
    status = 'активен' if quest.get('is_active', 1) else 'скрыт'
    return (
        f'📜 <b>{quest["title"]}</b>\n'
        f'ID: <code>{quest["id"]}</code>\n'
        f'Статус: <b>{status}</b>\n'
        f'Общий XP: <b>{quest["xp_reward"]}</b>\n'
        f'Общие монеты: <b>{quest["gold_reward"]}</b> 🪙\n'
        f'{item_line}\n\n'
        f'{quest["description"] or "Описание пока не добавлено."}'
    )


@router.callback_query(F.data == 'admin:quests')
async def admin_quests_menu(callback: CallbackQuery, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    await edit_or_answer(callback.message, '📜 <b>Квесты</b>\nЗдесь можно создать квест и одной кнопкой выдать награду выбранным персонажам.', reply_markup=quests_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == 'admin:quest_list')
async def admin_quest_list(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    quests = await db.list_quests(only_active=False)
    if not quests:
        await edit_or_answer(callback.message, 'Квестов пока нет.', reply_markup=quests_menu_keyboard())
        await callback.answer()
        return
    text = '📜 <b>Список квестов</b>\n\n' + '\n'.join(
        f'• #{quest["id"]} {"✅" if quest.get("is_active", 1) else "🚫"} <b>{quest["title"]}</b> — '
        f'{quest["xp_reward"]} XP, {quest["gold_reward"]} 🪙'
        for quest in quests
    )
    await edit_or_answer(callback.message, text, reply_markup=quests_keyboard(quests))
    await callback.answer()


@router.callback_query(F.data == 'admin:create_quest')
async def admin_create_quest_start(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    await state.clear()
    await state.set_state(CreateQuestState.title)
    await callback.message.answer('Введи название квеста. Например: <code>Спасти караван</code>')
    await callback.answer()


@router.message(CreateQuestState.title)
async def admin_create_quest_title(message: Message, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    title = message.text.strip()
    if len(title) < 2:
        await message.answer('Название слишком короткое. Введи название квеста ещё раз:')
        return
    await state.update_data(title=title)
    await state.set_state(CreateQuestState.description)
    await message.answer('Введи описание квеста:')


@router.message(CreateQuestState.description)
async def admin_create_quest_description(message: Message, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    await state.update_data(description=message.text.strip())
    await state.set_state(CreateQuestState.xp_reward)
    await message.answer('Введи общий XP за квест. При выдаче он будет разделён между выбранными игроками с округлением вверх. Например: <code>100</code>')


@router.message(CreateQuestState.xp_reward)
async def admin_create_quest_xp(message: Message, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    try:
        xp_reward = int(message.text.strip())
    except ValueError:
        await message.answer('Нужно ввести целое число. Например: <code>100</code>')
        return
    if xp_reward < 0:
        await message.answer('XP не может быть отрицательным. Введи ещё раз:')
        return
    await state.update_data(xp_reward=xp_reward)
    await state.set_state(CreateQuestState.gold_reward)
    await message.answer('Введи общую награду в монетах. Она тоже будет разделена между выбранными игроками с округлением вверх. Например: <code>75</code>')


@router.message(CreateQuestState.gold_reward)
async def admin_create_quest_gold(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    try:
        gold_reward = int(message.text.strip())
    except ValueError:
        await message.answer('Нужно ввести целое число. Например: <code>75</code>')
        return
    if gold_reward < 0:
        await message.answer('Монеты не могут быть отрицательными. Введи ещё раз:')
        return
    await state.update_data(gold_reward=gold_reward)
    await state.set_state(CreateQuestState.item_select)
    items = await db.list_items(only_active=False)
    await message.answer('Выбери предметную награду или вариант «Без предмета».', reply_markup=quest_item_reward_keyboard(items))


@router.callback_query(CreateQuestState.item_select, F.data.startswith('quest_item:'))
async def admin_create_quest_item(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    raw = callback.data.split(':')[1]
    if raw == 'none':
        await state.update_data(item_id=None, item_quantity=0)
        await finish_quest_creation(callback.message, state, db)
        await callback.answer()
        return
    await state.update_data(item_id=int(raw))
    await state.set_state(CreateQuestState.item_quantity)
    await callback.message.answer('Введи общее количество предметов для награды. Оно будет разделено между выбранными игроками с округлением вверх. Например: <code>3</code>')
    await callback.answer()


@router.message(CreateQuestState.item_quantity)
async def admin_create_quest_item_quantity(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    try:
        item_quantity = int(message.text.strip())
    except ValueError:
        await message.answer('Нужно ввести целое число. Например: <code>3</code>')
        return
    if item_quantity < 0:
        await message.answer('Количество не может быть отрицательным. Введи ещё раз:')
        return
    await state.update_data(item_quantity=item_quantity)
    await finish_quest_creation(message, state, db)


async def finish_quest_creation(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    quest_id = await db.create_quest(
        title=data['title'],
        description=data['description'],
        xp_reward=int(data['xp_reward']),
        gold_reward=int(data['gold_reward']),
        item_id=data.get('item_id'),
        item_quantity=int(data.get('item_quantity', 0)),
    )
    await state.clear()
    quest = await db.get_quest(quest_id)
    await message.answer('Квест создан ✅\n\n' + quest_text(quest), reply_markup=quest_details_keyboard(quest))


@router.callback_query(F.data.startswith('admin:quest:'))
async def admin_quest_details(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    quest_id = int(callback.data.split(':')[2])
    quest = await db.get_quest(quest_id)
    if quest is None:
        await callback.answer('Квест не найден.', show_alert=True)
        return
    await edit_or_answer(callback.message, quest_text(quest), reply_markup=quest_details_keyboard(quest))
    await callback.answer()


@router.callback_query(F.data.startswith('admin:quest_toggle:'))
async def admin_quest_toggle(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    quest_id = int(callback.data.split(':')[2])
    quest = await db.get_quest(quest_id)
    if quest is None:
        await callback.answer('Квест не найден.', show_alert=True)
        return
    await db.update_quest_active(quest_id, not bool(quest.get('is_active', 1)))
    updated = await db.get_quest(quest_id)
    await callback.answer('Статус квеста обновлён ✅')
    await edit_or_answer(callback.message, quest_text(updated), reply_markup=quest_details_keyboard(updated))


@router.callback_query(F.data.startswith('admin:quest_award:'))
async def admin_quest_award_start(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    quest_id = int(callback.data.split(':')[2])
    quest = await db.get_quest(quest_id)
    characters = await db.list_characters()
    if quest is None:
        await callback.answer('Квест не найден.', show_alert=True)
        return
    if not characters:
        await edit_or_answer(callback.message, 'Сначала создай хотя бы одного персонажа.', reply_markup=back_to_admin_menu())
        await callback.answer()
        return
    await state.clear()
    await state.update_data(quest_id=quest_id, selected_ids=[])
    await edit_or_answer(
        callback.message,
        f'Выбери персонажей, которым выдать награду за квест:\n<b>{quest["title"]}</b>',
        reply_markup=quest_award_characters_keyboard(characters, set()),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin:quest_select:'))
async def admin_quest_select_character(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    character_id = int(callback.data.split(':')[2])
    data = await state.get_data()
    selected = set(int(x) for x in data.get('selected_ids', []))
    if character_id in selected:
        selected.remove(character_id)
    else:
        selected.add(character_id)
    await state.update_data(selected_ids=list(selected))
    quest = await db.get_quest(int(data['quest_id']))
    characters = await db.list_characters()
    await edit_or_answer(
        callback.message,
        f'Выбери персонажей, которым выдать награду за квест:\n<b>{quest["title"]}</b>\n\nВыбрано: <b>{len(selected)}</b>',
        reply_markup=quest_award_characters_keyboard(characters, selected),
    )
    await callback.answer()


@router.callback_query(F.data == 'admin:quest_award_confirm')
async def admin_quest_award_confirm(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    data = await state.get_data()
    quest_id = data.get('quest_id')
    selected_ids = [int(x) for x in data.get('selected_ids', [])]
    if not quest_id or not selected_ids:
        await callback.answer('Нужно выбрать хотя бы одного персонажа.', show_alert=True)
        return
    success, result = await db.award_quest(int(quest_id), selected_ids, callback.from_user.id)
    await state.clear()
    await callback.answer('Готово ✅' if success else result, show_alert=not success)
    await callback.message.answer(result, reply_markup=back_to_admin_menu())


@router.callback_query(F.data == 'admin:quick_rewards')
async def admin_quick_rewards(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    sessions = await db.list_sessions(only_active=True)
    if not sessions:
        await edit_or_answer(callback.message, 'Сначала создай хотя бы одну активную сессию.', reply_markup=back_to_admin_menu())
        await callback.answer()
        return
    await edit_or_answer(
        callback.message,
        '⚡ <b>Быстрые награды</b>\n\nВыбери сессию. На следующем шаге можно одной кнопкой выдать XP и монеты всем персонажам этой сессии.',
        reply_markup=quick_reward_sessions_keyboard(sessions),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin:quick_reward_session:'))
async def admin_quick_reward_session(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    session_id = int(callback.data.split(':')[2])
    session = await db.get_session(session_id)
    if session is None:
        await callback.answer('Сессия не найдена.', show_alert=True)
        return
    await edit_or_answer(
        callback.message,
        f'⚡ <b>Быстрые награды</b>\n\n'
        f'Сессия: <b>{session["title"]}</b>\n'
        f'Персонажей: <b>{session.get("characters_count", 0)}</b>\n\n'
        'Выбери шаблон. Награда выдаётся каждому персонажу в этой сессии.',
        reply_markup=quick_reward_presets_keyboard(session_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin:quick_reward_apply:'))
async def admin_quick_reward_apply(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    _, _, session_id_raw, preset_key = callback.data.split(':')
    preset = QUICK_REWARD_PRESETS.get(preset_key)
    if not preset:
        await callback.answer('Шаблон награды не найден.', show_alert=True)
        return
    success, result = await db.grant_session_reward(
        int(session_id_raw),
        int(preset['xp']),
        int(preset['gold']),
        callback.from_user.id,
        note=f'Quick reward: {preset["title"]}',
    )
    await callback.answer('Награда выдана ✅' if success else result, show_alert=not success)
    await callback.message.answer(result, reply_markup=back_to_admin_menu())


@router.callback_query(F.data == 'admin:random_loot')
async def admin_random_loot_select_character(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    characters = await db.list_characters()
    if not characters:
        await edit_or_answer(callback.message, 'Сначала создай хотя бы одного персонажа.', reply_markup=back_to_admin_menu())
        await callback.answer()
        return
    loot_items = await db.list_loot_items()
    if not loot_items:
        await edit_or_answer(callback.message, 'Таблица рандомного лута пустая. Открой предмет и задай ему шанс лута больше 0%.', reply_markup=back_to_admin_menu())
        await callback.answer()
        return
    await edit_or_answer(callback.message, 'Кому кинуть рандомный лут?', reply_markup=characters_keyboard(characters, 'admin:random_loot_user'))
    await callback.answer()


@router.callback_query(F.data.startswith('admin:random_loot_user:'))
async def admin_random_loot_confirm(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    character_id = int(callback.data.split(':')[2])
    character = await db.get_character(character_id)
    if character is None:
        await callback.answer('Персонаж не найден.', show_alert=True)
        return
    await edit_or_answer(
        callback.message,
        f'🎲 Выдать рандомный лут персонажу <b>{character["display_name"]}</b>?\n\n'
        'Бот проверит все предметы, у которых шанс лута больше 0%, и выдаст те, которые выпадут.',
        reply_markup=random_loot_confirm_keyboard(character_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin:random_loot_roll:'))
async def admin_random_loot_roll(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    character_id = int(callback.data.split(':')[2])
    success, result = await db.roll_random_loot(character_id, callback.from_user.id)
    await callback.answer('Готово ✅' if success else result, show_alert=not success)
    await callback.message.answer(result, reply_markup=back_to_admin_menu())


@router.callback_query(F.data == 'admin:give_item')
async def give_item_select_character(callback: CallbackQuery, db: Database, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    characters = await db.list_characters()
    if not characters:
        await edit_or_answer(callback.message, 'Сначала создай хотя бы одного персонажа.', reply_markup=back_to_admin_menu())
        await callback.answer()
        return
    await state.clear()
    await edit_or_answer(callback.message, 'Кому выдать предмет?', reply_markup=characters_keyboard(characters, 'admin:give_user'))
    await callback.answer()


async def render_give_items_page(
    message: Message,
    db: Database,
    state: FSMContext,
    category_value: str | None = None,
    page: int = 0,
) -> None:
    data = await state.get_data()
    character_id = data.get('character_id')
    if not character_id:
        await edit_or_answer(message, 'Сначала выбери персонажа, кому выдать предмет.', reply_markup=back_to_admin_menu())
        return

    character = await db.get_character(int(character_id))
    if character is None:
        await edit_or_answer(message, 'Персонаж не найден. Выбери персонажа заново.', reply_markup=back_to_admin_menu())
        return

    categories = await db.list_categories(only_with_items=True, only_active=False)
    if not categories:
        await edit_or_answer(message, 'Сначала создай хотя бы один предмет.', reply_markup=back_to_admin_menu())
        return

    category_values = [category['value'] for category in categories]
    if not category_value or category_value not in category_values:
        category_value = category_values[0]

    category = next(category for category in categories if category['value'] == category_value)
    total_items = await db.count_items(only_active=False, category=category_value)
    total_pages = max(1, (total_items + PAGE_SIZE - 1) // PAGE_SIZE)
    safe_page = min(max(0, int(page)), total_pages - 1)
    items = await db.list_items(
        only_active=False,
        category=category_value,
        limit=PAGE_SIZE,
        offset=safe_page * PAGE_SIZE,
    )

    if items:
        lines = []
        for index, item in enumerate(items, start=safe_page * PAGE_SIZE + 1):
            active_mark = '' if item.get('is_active', 1) else '🚫 '
            lines.append(f'{index}. {active_mark}<b>{item["name"]}</b> — {item["price"]} 🪙 | {stock_label(item)}')
        items_text = '\n'.join(lines)
    else:
        items_text = 'В этой категории пока нет предметов.'

    text = (
        '🎁 <b>Выдача предмета</b>\n'
        f'Персонаж: <b>{character["display_name"]}</b>\n'
        f'Категория: <b>{category["title"]}</b>\n'
        f'Страница: <b>{safe_page + 1}/{total_pages}</b>\n'
        f'Всего в категории: <b>{total_items}</b>\n\n'
        'Показываю по 10 предметов. Выбери предмет, потом введёшь количество.\n\n'
        f'{items_text}'
    )
    await edit_or_answer(
        message,
        text,
        reply_markup=give_items_page_keyboard(items, categories, category_value, safe_page, total_pages),
    )


@router.callback_query(F.data.startswith('admin:give_user:'))
async def give_item_select_item(callback: CallbackQuery, db: Database, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    character_id = int(callback.data.split(':')[2])
    await state.update_data(character_id=character_id)
    await render_give_items_page(callback.message, db, state)
    await callback.answer()


@router.callback_query(F.data == 'admin:give_categories')
async def give_item_categories(callback: CallbackQuery, db: Database, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    data = await state.get_data()
    if not data.get('character_id'):
        await edit_or_answer(callback.message, 'Сначала выбери персонажа, кому выдать предмет.', reply_markup=back_to_admin_menu())
        await callback.answer()
        return
    categories = await db.list_categories(only_with_items=True, only_active=False)
    if not categories:
        await edit_or_answer(callback.message, 'Сначала создай хотя бы один предмет.', reply_markup=back_to_admin_menu())
        await callback.answer()
        return
    await edit_or_answer(
        callback.message,
        '📚 <b>Категории для выдачи предметов</b>\n\nВыбери категорию. Внутри будет максимум 10 предметов на странице.',
        reply_markup=categories_keyboard(categories, 'admin:give_category', 'admin:give_item', include_all=False),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin:give_category:'))
async def give_item_category(callback: CallbackQuery, db: Database, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    category = callback.data.split(':', 2)[2]
    await render_give_items_page(callback.message, db, state, category, 0)
    await callback.answer()


@router.callback_query(F.data.startswith('admin:give_page:'))
async def give_item_category_page(callback: CallbackQuery, db: Database, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    _, _, category, page_raw = callback.data.split(':')
    await render_give_items_page(callback.message, db, state, category, int(page_raw))
    await callback.answer()


@router.callback_query(F.data.startswith('admin:give_item_id:'))
async def give_item_enter_quantity(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    item_id = int(callback.data.split(':')[2])
    await state.update_data(item_id=item_id)
    await state.set_state(GiveItemState.quantity)
    await callback.message.answer('Введи количество предметов. Можно отрицательное число, если нужно забрать предмет.')
    await callback.answer()


@router.message(GiveItemState.quantity)
async def give_item_finish(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    try:
        quantity = int(message.text.strip())
    except ValueError:
        await message.answer('Нужно ввести целое число. Например: <code>1</code> или <code>-1</code>')
        return
    data = await state.get_data()
    character_id = int(data['character_id'])
    item_id = int(data['item_id'])
    await db.add_item_to_inventory(character_id, item_id, quantity, message.from_user.id)
    character = await db.get_character(character_id)
    item = await db.get_item(item_id)
    await state.clear()
    carry = await db.get_character_carry_info(character_id)
    await message.answer(
        f'Готово ✅\n'
        f'Персонаж: <b>{character["display_name"]}</b>\n'
        f'Предмет: <b>{item["name"]}</b>\n'
        f'Количество: <b>{quantity}</b>\n\n'
        f'🎒 <b>Вес после выдачи</b>\n{carry_info_text(carry)}',
        reply_markup=back_to_admin_menu(),
    )
