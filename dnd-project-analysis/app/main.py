from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand

from app.config import load_settings
from app.backup_service import backup_loop
from app.database import Database
from app.handlers import admin, assistant, common, player


def configure_logging(level_name: str) -> None:
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        force=True,
    )


async def setup_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command='start', description='Запустить бота'),
            BotCommand(command='menu', description='Главное меню'),
            BotCommand(command='login', description='Войти в персонажа'),
            BotCommand(command='logout', description='Выйти из персонажа'),
            BotCommand(command='profile', description='Профиль персонажа'),
            BotCommand(command='journal', description='Журнал персонажа'),
            BotCommand(command='inventory', description='Инвентарь'),
            BotCommand(command='shop', description='Магазин'),
            BotCommand(command='find', description='Найти предмет'),
            BotCommand(command='transfer', description='Передать монеты или предмет'),
            BotCommand(command='levels', description='Таблица уровней DnD'),
            BotCommand(command='admin', description='Админ-панель'),
            BotCommand(command='cancel', description='Отменить действие'),
        ]
    )


async def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    db = Database(settings.database_path)
    await db.init()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = RedisStorage.from_url(settings.redis_url)
    dp = Dispatcher(storage=storage)

    dp['settings'] = settings
    dp['db'] = db

    dp.include_router(common.router)
    dp.include_router(player.router)
    dp.include_router(assistant.router)
    dp.include_router(admin.router)

    await setup_bot_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    logging.getLogger(__name__).info('Bot started in long polling mode')
    backup_task = asyncio.create_task(
        backup_loop(
            settings.database_path,
            settings.backup_dir,
            settings.backup_interval_hours,
            settings.backup_retention_days,
        ),
        name='database-backup-loop',
    )
    try:
        await dp.start_polling(bot)
    finally:
        backup_task.cancel()
        await asyncio.gather(backup_task, return_exceptions=True)
        await storage.close()
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
