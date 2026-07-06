from __future__ import annotations

from dataclasses import dataclass
from os import getenv
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: set[int]
    database_path: str
    campaign_name: str


def _parse_admin_ids(raw_value: str | None) -> set[int]:
    if not raw_value:
        return set()

    result: set[int] = set()
    for part in raw_value.split(','):
        value = part.strip()
        if not value:
            continue
        try:
            result.add(int(value))
        except ValueError as exc:
            raise ValueError(f'TELEGRAM_ADMIN_IDS contains invalid value: {value}') from exc
    return result


def load_settings() -> Settings:
    load_dotenv()

    bot_token = getenv('BOT_TOKEN')
    if not bot_token:
        raise RuntimeError('BOT_TOKEN is not set. Copy .env.example to .env and fill it.')

    database_path = getenv('DATABASE_PATH', './data/dnd_bot.sqlite3')
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)

    return Settings(
        bot_token=bot_token,
        admin_ids=_parse_admin_ids(getenv('TELEGRAM_ADMIN_IDS')),
        database_path=database_path,
        campaign_name=getenv('CAMPAIGN_NAME', 'DnD Campaign'),
    )
