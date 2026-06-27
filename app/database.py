from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.security import create_password_hash, verify_password


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Database:
    def __init__(self, path: str):
        self.path = path

    async def connect(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute('PRAGMA foreign_keys = ON')
        return db

    async def init(self) -> None:
        async with await self.connect() as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS characters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE,
                    login TEXT NOT NULL UNIQUE,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0,
                    gold INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT
                );

                CREATE TABLE IF NOT EXISTS shop_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    price INTEGER NOT NULL DEFAULT 0,
                    rarity TEXT NOT NULL DEFAULT 'common',
                    image_file_id TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS inventory (
                    character_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (character_id, item_id),
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE,
                    FOREIGN KEY (item_id) REFERENCES shop_items(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    character_id INTEGER,
                    admin_telegram_id INTEGER,
                    type TEXT NOT NULL,
                    amount INTEGER,
                    item_id INTEGER,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE SET NULL,
                    FOREIGN KEY (item_id) REFERENCES shop_items(id) ON DELETE SET NULL
                );
                """
            )
            await db.commit()

    async def create_character(self, login: str, password: str, display_name: str) -> int:
        salt, password_hash = create_password_hash(password)
        async with await self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO characters(login, password_salt, password_hash, display_name, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (login.strip(), salt, password_hash, display_name.strip(), now_iso()),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def authenticate_character(self, login: str, password: str, telegram_id: int) -> dict[str, Any] | None:
        async with await self.connect() as db:
            cursor = await db.execute(
                'SELECT * FROM characters WHERE login = ?',
                (login.strip(),),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            if not verify_password(password, row['password_salt'], row['password_hash']):
                return None
            if row['telegram_id'] is not None and row['telegram_id'] != telegram_id:
                raise PermissionError('Этот персонаж уже привязан к другому Telegram аккаунту.')
            await db.execute(
                'UPDATE characters SET telegram_id = ?, last_login_at = ? WHERE id = ?',
                (telegram_id, now_iso(), row['id']),
            )
            await db.commit()
            updated = await db.execute('SELECT * FROM characters WHERE id = ?', (row['id'],))
            return dict(await updated.fetchone())

    async def unlink_character(self, telegram_id: int) -> None:
        async with await self.connect() as db:
            await db.execute('UPDATE characters SET telegram_id = NULL WHERE telegram_id = ?', (telegram_id,))
            await db.commit()

    async def get_character_by_telegram_id(self, telegram_id: int) -> dict[str, Any] | None:
        async with await self.connect() as db:
            cursor = await db.execute('SELECT * FROM characters WHERE telegram_id = ?', (telegram_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_character(self, character_id: int) -> dict[str, Any] | None:
        async with await self.connect() as db:
            cursor = await db.execute('SELECT * FROM characters WHERE id = ?', (character_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_characters(self) -> list[dict[str, Any]]:
        async with await self.connect() as db:
            cursor = await db.execute(
                'SELECT * FROM characters ORDER BY display_name COLLATE NOCASE ASC'
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def add_xp(self, character_id: int, amount: int, admin_telegram_id: int | None = None, note: str | None = None) -> None:
        async with await self.connect() as db:
            await db.execute(
                'UPDATE characters SET xp = MAX(0, xp + ?) WHERE id = ?',
                (amount, character_id),
            )
            await db.execute(
                """
                INSERT INTO transactions(character_id, admin_telegram_id, type, amount, note, created_at)
                VALUES (?, ?, 'xp', ?, ?, ?)
                """,
                (character_id, admin_telegram_id, amount, note, now_iso()),
            )
            await db.commit()

    async def add_gold(self, character_id: int, amount: int, admin_telegram_id: int | None = None, note: str | None = None) -> None:
        async with await self.connect() as db:
            await db.execute(
                'UPDATE characters SET gold = MAX(0, gold + ?) WHERE id = ?',
                (amount, character_id),
            )
            await db.execute(
                """
                INSERT INTO transactions(character_id, admin_telegram_id, type, amount, note, created_at)
                VALUES (?, ?, 'gold', ?, ?, ?)
                """,
                (character_id, admin_telegram_id, amount, note, now_iso()),
            )
            await db.commit()

    async def create_item(self, name: str, description: str, price: int, rarity: str, image_file_id: str | None) -> int:
        async with await self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO shop_items(name, description, price, rarity, image_file_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name.strip(), description.strip(), max(0, price), rarity.strip(), image_file_id, now_iso()),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def update_item_active(self, item_id: int, is_active: bool) -> None:
        async with await self.connect() as db:
            await db.execute('UPDATE shop_items SET is_active = ? WHERE id = ?', (1 if is_active else 0, item_id))
            await db.commit()

    async def list_items(self, only_active: bool = True) -> list[dict[str, Any]]:
        query = 'SELECT * FROM shop_items'
        params: tuple[Any, ...] = ()
        if only_active:
            query += ' WHERE is_active = 1'
        query += ' ORDER BY name COLLATE NOCASE ASC'
        async with await self.connect() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_item(self, item_id: int) -> dict[str, Any] | None:
        async with await self.connect() as db:
            cursor = await db.execute('SELECT * FROM shop_items WHERE id = ?', (item_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def add_item_to_inventory(
        self,
        character_id: int,
        item_id: int,
        quantity: int,
        admin_telegram_id: int | None = None,
        note: str | None = None,
    ) -> None:
        if quantity == 0:
            return
        async with await self.connect() as db:
            await db.execute(
                """
                INSERT INTO inventory(character_id, item_id, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(character_id, item_id)
                DO UPDATE SET quantity = MAX(0, inventory.quantity + excluded.quantity)
                """,
                (character_id, item_id, quantity),
            )
            await db.execute('DELETE FROM inventory WHERE quantity <= 0')
            await db.execute(
                """
                INSERT INTO transactions(character_id, admin_telegram_id, type, amount, item_id, note, created_at)
                VALUES (?, ?, 'item', ?, ?, ?, ?)
                """,
                (character_id, admin_telegram_id, quantity, item_id, note, now_iso()),
            )
            await db.commit()

    async def list_inventory(self, character_id: int) -> list[dict[str, Any]]:
        async with await self.connect() as db:
            cursor = await db.execute(
                """
                SELECT i.quantity, si.*
                FROM inventory i
                JOIN shop_items si ON si.id = i.item_id
                WHERE i.character_id = ? AND i.quantity > 0
                ORDER BY si.name COLLATE NOCASE ASC
                """,
                (character_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def buy_item(self, character_id: int, item_id: int, quantity: int = 1) -> tuple[bool, str]:
        if quantity <= 0:
            return False, 'Количество должно быть больше 0.'

        async with await self.connect() as db:
            item_cursor = await db.execute('SELECT * FROM shop_items WHERE id = ? AND is_active = 1', (item_id,))
            item = await item_cursor.fetchone()
            if item is None:
                return False, 'Предмет не найден или скрыт из магазина.'

            character_cursor = await db.execute('SELECT gold FROM characters WHERE id = ?', (character_id,))
            character = await character_cursor.fetchone()
            if character is None:
                return False, 'Персонаж не найден.'

            total_price = int(item['price']) * quantity
            if int(character['gold']) < total_price:
                return False, f'Не хватает монет. Нужно {total_price}, у тебя {character["gold"]}.'

            await db.execute('UPDATE characters SET gold = gold - ? WHERE id = ?', (total_price, character_id))
            await db.execute(
                """
                INSERT INTO inventory(character_id, item_id, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(character_id, item_id)
                DO UPDATE SET quantity = inventory.quantity + excluded.quantity
                """,
                (character_id, item_id, quantity),
            )
            await db.execute(
                """
                INSERT INTO transactions(character_id, type, amount, item_id, note, created_at)
                VALUES (?, 'buy', ?, ?, ?, ?)
                """,
                (character_id, quantity, item_id, f'Bought for {total_price} gold', now_iso()),
            )
            await db.commit()
            return True, f'Покупка успешна: {item["name"]} ×{quantity}. Списано {total_price} монет.'
