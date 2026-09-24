from __future__ import annotations

import os
import sqlite3
from pathlib import Path


REQUIRED_TABLES = {
    'app_migrations',
    'auth_attempts',
    'character_equipment',
    'character_journal',
    'character_sheet_entries',
    'character_sheets',
    'characters',
    'game_sessions',
    'inventory',
    'item_categories',
    'quest_awards',
    'quests',
    'shop_items',
    'transactions',
}


def check_database(database_path: str) -> tuple[bool, str]:
    path = Path(database_path)
    if not path.is_file():
        return False, 'database file is missing'

    connection = None
    try:
        connection = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5)
        quick_check = connection.execute('PRAGMA quick_check(1)').fetchone()
        if not quick_check or quick_check[0] != 'ok':
            return False, 'sqlite quick_check failed'
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        missing = sorted(REQUIRED_TABLES - tables)
        if missing:
            return False, 'missing tables: ' + ', '.join(missing)
        return True, 'ok'
    except sqlite3.Error as exc:
        return False, f'sqlite error: {exc}'
    finally:
        if connection is not None:
            connection.close()


def main() -> int:
    database_path = os.getenv('DATABASE_PATH', '/app/data/dnd_bot.sqlite3')
    healthy, message = check_database(database_path)
    print(message)
    return 0 if healthy else 1


if __name__ == '__main__':
    raise SystemExit(main())
