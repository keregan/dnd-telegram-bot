from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.database import Database
from app.handlers.common import is_admin
from app.keyboards import admin_menu, back_to_admin_menu, characters_keyboard, items_keyboard, rarity_keyboard
from app.states import AdminNumberState, CreateCharacterState, CreateItemState, GiveItemState
from app.ui import edit_or_answer

router = Router(name='admin')


def character_short(character: dict) -> str:
    tg = 'привязан' if character.get('telegram_id') else 'не привязан'
    return (
        f'<b>{character["display_name"]}</b>\n'
        f'Логин: <code>{character["login"]}</code>\n'
        f'XP: <b>{character["xp"]}</b>\n'
        f'Монеты: <b>{character["gold"]}</b> 🪙\n'
        f'Telegram: {tg}'
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
    if action == 'xp':
        await db.add_xp(character_id, amount, message.from_user.id)
        label = 'XP'
    else:
        await db.add_gold(character_id, amount, message.from_user.id)
        label = 'монет'

    character = await db.get_character(character_id)
    await state.clear()
    await message.answer(
        f'Готово ✅\n'
        f'{character["display_name"]}: {label} изменены на <b>{amount}</b>.\n'
        f'Текущий XP: <b>{character["xp"]}</b>\n'
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
    await message.answer('Введи цену предмета в монетах. Например: <code>10</code>')


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
    await state.set_state(CreateItemState.photo)
    await callback.message.answer('Отправь картинку предмета одним фото. Если картинка не нужна — напиши /skip')
    await callback.answer()


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
    )
    await state.clear()
    await message.answer(
        'Предмет создан ✅\n\n'
        f'ID: <code>{item_id}</code>\n'
        f'Название: <b>{data["name"]}</b>\n'
        f'Цена: <b>{data["price"]}</b> 🪙\n'
        f'Редкость: <b>{data["rarity"]}</b>',
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
        f'• #{item["id"]} {"✅" if item["is_active"] else "🚫"} <b>{item["name"]}</b> — {item["price"]} 🪙, {item["rarity"]}'
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
    status = 'активен в магазине' if item['is_active'] else 'скрыт из магазина'
    text = (
        f'<b>{item["name"]}</b>\n'
        f'ID: <code>{item["id"]}</code>\n'
        f'Статус: <b>{status}</b>\n'
        f'Редкость: <b>{item["rarity"]}</b>\n'
        f'Цена: <b>{item["price"]}</b> 🪙\n\n'
        f'{item["description"]}'
    )
    if item.get('image_file_id'):
        await callback.message.answer_photo(item['image_file_id'], caption=text, reply_markup=back_to_admin_menu())
    else:
        await callback.message.answer(text, reply_markup=back_to_admin_menu())
    await callback.answer()


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
