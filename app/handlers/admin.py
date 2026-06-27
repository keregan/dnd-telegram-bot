from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.database import Database
from app.handlers.common import is_admin
from app.keyboards import (
    admin_item_manage_keyboard,
    admin_menu,
    back_to_admin_menu,
    characters_keyboard,
    item_availability_keyboard,
    items_keyboard,
    quest_award_characters_keyboard,
    quest_details_keyboard,
    quest_item_reward_keyboard,
    quests_keyboard,
    quests_menu_keyboard,
    random_loot_confirm_keyboard,
    rarity_keyboard,
    stock_label,
)
from app.levels import level_progress_text
from app.states import (
    AdminNumberState,
    CreateCharacterState,
    CreateItemState,
    CreateQuestState,
    GiveItemState,
    SetItemLootChanceState,
    SetItemStockState,
)
from app.ui import edit_or_answer

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
    return (
        f'<b>{item["name"]}</b>\n'
        f'ID: <code>{item["id"]}</code>\n'
        f'Статус: <b>{status}</b>\n'
        f'Остаток в магазине: <b>{stock_label(item)}</b>\n'
        f'Редкость: <b>{item["rarity"]}</b>\n'
        f'Цена продажи/покупки: <b>{item["price"]}</b> 🪙\n\n'
        f'{item["description"] or "Описание пока не добавлено."}'
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
    await message.answer(
        'Персонаж создан ✅\n\n'
        f'ID: <code>{character_id}</code>\n'
        f'Имя: <b>{display_name}</b>\n'
        f'Логин: <code>{data["login"]}</code>\n'
        f'Пароль: <code>{data["password"]}</code>\n\n'
        'Передай логин и пароль игроку. Пароль в базе хранится в виде хэша.',
        reply_markup=back_to_admin_menu(),
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
    text = '👥 <b>Персонажи</b>\n\n' + '\n\n'.join(character_short(character) for character in characters)
    await edit_or_answer(callback.message, text, reply_markup=back_to_admin_menu())
    await callback.answer()


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
async def create_item_description(message: Message, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(message, settings):
        return
    await state.update_data(description=message.text.strip())
    await state.set_state(CreateItemState.price)
    await message.answer('Введи цену предмета в монетах. Эта цена используется и для покупки, и для продажи. Например: <code>10</code>')


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
        image_file_id=image_file_id,
        is_active=bool(data.get('is_active', True)),
        shop_quantity=int(data.get('shop_quantity', -1)),
        loot_chance_percent=int(data.get('loot_chance_percent', 0)),
    )
    await state.clear()
    availability = 'в магазине' if data.get('is_active', True) else 'только для выдачи игрокам'
    stock = data.get('shop_quantity', -1)
    stock_text = 'без лимита' if int(stock) < 0 else str(stock)
    await message.answer(
        'Предмет создан ✅\n\n'
        f'ID: <code>{item_id}</code>\n'
        f'Название: <b>{data["name"]}</b>\n'
        f'Цена: <b>{data["price"]}</b> 🪙\n'
        f'Редкость: <b>{data["rarity"]}</b>\n'
        f'Доступность: <b>{availability}</b>\n'
        f'Остаток в магазине: <b>{stock_text}</b>',
        reply_markup=back_to_admin_menu(),
    )


@router.callback_query(F.data == 'admin:items')
async def admin_items(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    items = await db.list_items(only_active=False)
    if not items:
        await edit_or_answer(callback.message, 'Предметов пока нет.', reply_markup=back_to_admin_menu())
        await callback.answer()
        return
    text = '📦 <b>Все предметы</b>\n\n' + '\n'.join(
        f'• #{item["id"]} {"✅" if item["is_active"] else "🚫"} <b>{item["name"]}</b> — '
        f'{item["price"]} 🪙, {item["rarity"]}, остаток: {stock_label(item)}, лут: {item.get("loot_chance_percent", 0)}%'
        for item in items
    )
    await edit_or_answer(callback.message, text, reply_markup=items_keyboard(items, 'admin:item', 'admin:menu'))
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
    if item.get('image_file_id'):
        await callback.message.answer_photo(item['image_file_id'], caption=text, reply_markup=admin_item_manage_keyboard(item))
    else:
        await callback.message.answer(text, reply_markup=admin_item_manage_keyboard(item))
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


@router.callback_query(F.data.startswith('admin:give_user:'))
async def give_item_select_item(callback: CallbackQuery, db: Database, state: FSMContext, settings: Settings) -> None:
    if await deny_if_not_admin(callback, settings):
        return
    character_id = int(callback.data.split(':')[2])
    items = await db.list_items(only_active=False)
    if not items:
        await edit_or_answer(callback.message, 'Сначала создай хотя бы один предмет.', reply_markup=back_to_admin_menu())
        await callback.answer()
        return
    await state.update_data(character_id=character_id)
    await edit_or_answer(callback.message, 'Какой предмет выдать?', reply_markup=items_keyboard(items, 'admin:give_item_id', 'admin:menu'))
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
    await message.answer(
        f'Готово ✅\n'
        f'Персонаж: <b>{character["display_name"]}</b>\n'
        f'Предмет: <b>{item["name"]}</b>\n'
        f'Количество: <b>{quantity}</b>',
        reply_markup=back_to_admin_menu(),
    )
