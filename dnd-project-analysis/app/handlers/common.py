from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.database import Database
from app.feature_visibility import HIDDEN_GAME_COMMANDS, HIDDEN_GAME_MESSAGE, is_hidden_game_callback
from app.keyboards import main_menu
from app.levels import level_progress_text
from app.states import LoginState
from app.ui import edit_or_answer

router = Router(name='common')


def is_admin(user_id: int | None, settings: Settings) -> bool:
    return user_id in settings.admin_ids if user_id is not None else False


def main_menu_text(character: dict | None, settings: Settings) -> str:
    if character is None:
        return (
            f'Привет! Это бот кампании <b>{settings.campaign_name}</b>.\n\n'
            'Здесь можно смотреть профиль, опыт, монеты, инвентарь и покупать предметы в магазине.\n\n'
            'Если у тебя уже есть логин и пароль от мастера — нажми «Войти».'
        )
    return (
        f'🎲 <b>{settings.campaign_name}</b>\n\n'
        f'Ты вошёл как <b>{character["display_name"]}</b>.\n'
        f'Монеты: <b>{character["gold"]}</b> 🪙\n'
        f'{level_progress_text(character)}\n\n'
        'Выбери действие:'
    )


@router.message(Command(*sorted(HIDDEN_GAME_COMMANDS)))
async def hidden_game_command(message: Message) -> None:
    await message.answer(HIDDEN_GAME_MESSAGE)


@router.callback_query(lambda callback: is_hidden_game_callback(callback.data))
async def hidden_game_callback(callback: CallbackQuery) -> None:
    await callback.answer(HIDDEN_GAME_MESSAGE, show_alert=True)


@router.message(CommandStart())
async def start(message: Message, db: Database, settings: Settings) -> None:
    character = await db.get_character_by_telegram_id(message.from_user.id)
    await message.answer(
        main_menu_text(character, settings),
        reply_markup=main_menu(is_admin(message.from_user.id, settings), character is not None),
    )


@router.message(Command('menu'))
async def menu_command(message: Message, db: Database, settings: Settings) -> None:
    character = await db.get_character_by_telegram_id(message.from_user.id)
    await message.answer(
        main_menu_text(character, settings),
        reply_markup=main_menu(is_admin(message.from_user.id, settings), character is not None),
    )


@router.callback_query(F.data == 'menu:main')
async def menu_callback(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    character = await db.get_character_by_telegram_id(callback.from_user.id)
    await edit_or_answer(
        callback.message,
        main_menu_text(character, settings),
        reply_markup=main_menu(is_admin(callback.from_user.id, settings), character is not None),
    )
    await callback.answer()


@router.message(Command('login'))
async def login_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(LoginState.login)
    await message.answer('Введи логин персонажа:')


@router.callback_query(F.data == 'auth:login')
async def login_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(LoginState.login)
    await callback.message.answer('Введи логин персонажа:')
    await callback.answer()


@router.message(LoginState.login)
async def login_entered(message: Message, state: FSMContext) -> None:
    await state.update_data(login=message.text.strip())
    await state.set_state(LoginState.password)
    await message.answer('Теперь введи пароль:')


@router.message(LoginState.password)
async def password_entered(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    data = await state.get_data()
    login = data.get('login', '').strip()
    password = message.text.strip()

    try:
        character = await db.authenticate_character(login, password, message.from_user.id)
    except PermissionError as exc:
        await state.clear()
        await message.answer(str(exc), reply_markup=main_menu(is_admin(message.from_user.id, settings), False))
        return

    await state.clear()
    if character is None:
        await message.answer('Логин или пароль не подошли. Попробуй ещё раз командой /login.')
        return

    await message.answer(
        f'Готово! Ты вошёл как <b>{character["display_name"]}</b>.\n\n'
        f'Монеты: <b>{character["gold"]}</b> 🪙\n'
        f'{level_progress_text(character)}',
        reply_markup=main_menu(is_admin(message.from_user.id, settings), character is not None),
    )


@router.message(Command('logout'))
async def logout_command(message: Message, db: Database, settings: Settings) -> None:
    await db.unlink_character(message.from_user.id)
    await message.answer('Ты вышел из персонажа. Для входа используй /login.', reply_markup=main_menu(is_admin(message.from_user.id, settings), False))


@router.callback_query(F.data == 'auth:logout')
async def logout_callback(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    await db.unlink_character(callback.from_user.id)
    await edit_or_answer(
        callback.message,
        'Ты вышел из аккаунта персонажа. Для входа используй /login или кнопку «Войти».',
        reply_markup=main_menu(is_admin(callback.from_user.id, settings), False),
    )
    await callback.answer('Готово ✅')


@router.message(Command('cancel'))
async def cancel_command(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    await message.answer('Действие отменено.', reply_markup=main_menu(is_admin(message.from_user.id, settings), False))


@router.callback_query(F.data == 'noop')
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()
