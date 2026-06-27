from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.config import load_settings
from app.database import Database
from app.handlers import admin, common, player


async def setup_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command='start', description='Запустить бота'),
            BotCommand(command='menu', description='Главное меню'),
            BotCommand(command='login', description='Войти в персонажа'),
            BotCommand(command='logout', description='Выйти из персонажа'),
            BotCommand(command='profile', description='Профиль персонажа'),
            BotCommand(command='inventory', description='Инвентарь'),
            BotCommand(command='shop', description='Магазин'),
            BotCommand(command='admin', description='Админ-панель'),
            BotCommand(command='cancel', description='Отменить действие'),
        ]
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')

    settings = load_settings()
    db = Database(settings.database_path)
    await db.init()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp['settings'] = settings
    dp['db'] = db

    dp.include_router(common.router)
    dp.include_router(player.router)
    dp.include_router(admin.router)

    await setup_bot_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info('Bot started in long polling mode')
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
