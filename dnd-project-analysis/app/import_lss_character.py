from __future__ import annotations

import argparse
import asyncio
import json
import os

from dotenv import load_dotenv

from app.character_sheet import parse_lss_character
from app.database import Database


async def run(path: str, password: str, spell_catalog_path: str | None) -> None:
    load_dotenv()
    catalog = None
    if spell_catalog_path:
        with open(spell_catalog_path, encoding='utf-8-sig') as source:
            raw = json.load(source)
        catalog = {str(item['id']): item for item in raw} if isinstance(raw, list) else raw
    sheet = parse_lss_character(path, catalog)
    database = Database(os.getenv('DATABASE_PATH', './data/dnd_bot.sqlite3'))
    await database.init()
    result = await database.import_character_sheet(sheet, password)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description='Import a Long Story Short character into the bot database.')
    parser.add_argument('path')
    parser.add_argument('--password', default='12345')
    parser.add_argument('--spell-catalog')
    args = parser.parse_args()
    asyncio.run(run(args.path, args.password, args.spell_catalog))


if __name__ == '__main__':
    main()
