from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
import random

import aiosqlite

from app.levels import enrich_character
from app.security import create_password_hash, verify_password


UNLIMITED_STOCK = -1


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Database:
    def __init__(self, path: str):
        self.path = path

    @asynccontextmanager
    async def connect(self):
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute('PRAGMA foreign_keys = ON')
        try:
            yield db
        finally:
            await db.close()

    async def _ensure_column(self, db: aiosqlite.Connection, table: str, column: str, ddl: str) -> None:
        cursor = await db.execute(f'PRAGMA table_info({table})')
        columns = {row['name'] for row in await cursor.fetchall()}
        if column not in columns:
            await db.execute(f'ALTER TABLE {table} ADD COLUMN {ddl}')

    async def init(self) -> None:
        async with self.connect() as db:
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
                    shop_quantity INTEGER NOT NULL DEFAULT -1,
                    loot_chance_percent INTEGER NOT NULL DEFAULT 0,
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

                CREATE TABLE IF NOT EXISTS quests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    xp_reward INTEGER NOT NULL DEFAULT 0,
                    gold_reward INTEGER NOT NULL DEFAULT 0,
                    item_id INTEGER,
                    item_quantity INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (item_id) REFERENCES shop_items(id) ON DELETE SET NULL
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
            await self._ensure_column(db, 'shop_items', 'shop_quantity', 'shop_quantity INTEGER NOT NULL DEFAULT -1')
            await self._ensure_column(db, 'shop_items', 'loot_chance_percent', 'loot_chance_percent INTEGER NOT NULL DEFAULT 0')
            await db.commit()

    async def create_character(self, login: str, password: str, display_name: str) -> int:
        salt, password_hash = create_password_hash(password)
        async with self.connect() as db:
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
        async with self.connect() as db:
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
            updated_row = await updated.fetchone()
            return enrich_character(dict(updated_row))

    async def unlink_character(self, telegram_id: int) -> None:
        async with self.connect() as db:
            await db.execute('UPDATE characters SET telegram_id = NULL WHERE telegram_id = ?', (telegram_id,))
            await db.commit()

    async def get_character_by_telegram_id(self, telegram_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            cursor = await db.execute('SELECT * FROM characters WHERE telegram_id = ?', (telegram_id,))
            row = await cursor.fetchone()
            return enrich_character(dict(row)) if row else None

    async def get_character(self, character_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            cursor = await db.execute('SELECT * FROM characters WHERE id = ?', (character_id,))
            row = await cursor.fetchone()
            return enrich_character(dict(row)) if row else None

    async def list_characters(self) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute('SELECT * FROM characters ORDER BY display_name COLLATE NOCASE ASC')
            rows = await cursor.fetchall()
            return [enrich_character(dict(row)) for row in rows]

    async def add_xp(self, character_id: int, amount: int, admin_telegram_id: int | None = None, note: str | None = None) -> None:
        async with self.connect() as db:
            await db.execute('UPDATE characters SET xp = MAX(0, xp + ?) WHERE id = ?', (amount, character_id))
            await db.execute(
                """
                INSERT INTO transactions(character_id, admin_telegram_id, type, amount, note, created_at)
                VALUES (?, ?, 'xp', ?, ?, ?)
                """,
                (character_id, admin_telegram_id, amount, note, now_iso()),
            )
            await db.commit()

    async def add_gold(self, character_id: int, amount: int, admin_telegram_id: int | None = None, note: str | None = None) -> None:
        async with self.connect() as db:
            await db.execute('UPDATE characters SET gold = MAX(0, gold + ?) WHERE id = ?', (amount, character_id))
            await db.execute(
                """
                INSERT INTO transactions(character_id, admin_telegram_id, type, amount, note, created_at)
                VALUES (?, ?, 'gold', ?, ?, ?)
                """,
                (character_id, admin_telegram_id, amount, note, now_iso()),
            )
            await db.commit()

    async def create_item(
        self,
        name: str,
        description: str,
        price: int,
        rarity: str,
        image_file_id: str | None,
        is_active: bool = True,
        shop_quantity: int = UNLIMITED_STOCK,
        loot_chance_percent: int = 0,
    ) -> int:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO shop_items(name, description, price, rarity, image_file_id, is_active, shop_quantity, loot_chance_percent, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name.strip(),
                    description.strip(),
                    max(0, price),
                    rarity.strip(),
                    image_file_id,
                    1 if is_active else 0,
                    max(UNLIMITED_STOCK, shop_quantity),
                    min(100, max(0, loot_chance_percent)),
                    now_iso(),
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def update_item_active(self, item_id: int, is_active: bool) -> None:
        async with self.connect() as db:
            await db.execute('UPDATE shop_items SET is_active = ? WHERE id = ?', (1 if is_active else 0, item_id))
            await db.commit()

    async def update_item_stock(self, item_id: int, shop_quantity: int) -> None:
        async with self.connect() as db:
            await db.execute('UPDATE shop_items SET shop_quantity = ? WHERE id = ?', (max(UNLIMITED_STOCK, shop_quantity), item_id))
            await db.commit()

    async def update_item_loot_chance(self, item_id: int, chance_percent: int) -> None:
        async with self.connect() as db:
            await db.execute(
                'UPDATE shop_items SET loot_chance_percent = ? WHERE id = ?',
                (min(100, max(0, chance_percent)), item_id),
            )
            await db.commit()

    async def list_loot_items(self) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute(
                'SELECT * FROM shop_items WHERE loot_chance_percent > 0 ORDER BY loot_chance_percent DESC, name COLLATE NOCASE ASC'
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def list_items(self, only_active: bool = True) -> list[dict[str, Any]]:
        query = 'SELECT * FROM shop_items'
        params: tuple[Any, ...] = ()
        if only_active:
            query += ' WHERE is_active = 1'
        query += ' ORDER BY name COLLATE NOCASE ASC'
        async with self.connect() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_item(self, item_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
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
        async with self.connect() as db:
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
        async with self.connect() as db:
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

        async with self.connect() as db:
            item_cursor = await db.execute('SELECT * FROM shop_items WHERE id = ? AND is_active = 1', (item_id,))
            item = await item_cursor.fetchone()
            if item is None:
                return False, 'Предмет не найден или скрыт из магазина.'

            shop_quantity = int(item['shop_quantity'])
            if shop_quantity == 0:
                return False, 'Этот предмет закончился в магазине.'
            if shop_quantity > 0 and shop_quantity < quantity:
                return False, f'В магазине осталось только {shop_quantity} шт.'

            character_cursor = await db.execute('SELECT gold FROM characters WHERE id = ?', (character_id,))
            character = await character_cursor.fetchone()
            if character is None:
                return False, 'Персонаж не найден.'

            total_price = int(item['price']) * quantity
            if int(character['gold']) < total_price:
                return False, f'Не хватает монет. Нужно {total_price}, у тебя {character["gold"]}.'

            await db.execute('UPDATE characters SET gold = gold - ? WHERE id = ?', (total_price, character_id))
            if shop_quantity > 0:
                await db.execute('UPDATE shop_items SET shop_quantity = shop_quantity - ? WHERE id = ?', (quantity, item_id))
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

    async def sell_item(self, character_id: int, item_id: int, quantity: int = 1) -> tuple[bool, str]:
        if quantity <= 0:
            return False, 'Количество должно быть больше 0.'

        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT i.quantity, si.name, si.price
                FROM inventory i
                JOIN shop_items si ON si.id = i.item_id
                WHERE i.character_id = ? AND i.item_id = ?
                """,
                (character_id, item_id),
            )
            row = await cursor.fetchone()
            if row is None or int(row['quantity']) <= 0:
                return False, 'Такого предмета нет в инвентаре.'
            if int(row['quantity']) < quantity:
                return False, f'У тебя есть только {row["quantity"]} шт.'

            total_price = int(row['price']) * quantity
            await db.execute(
                'UPDATE inventory SET quantity = quantity - ? WHERE character_id = ? AND item_id = ?',
                (quantity, character_id, item_id),
            )
            await db.execute('DELETE FROM inventory WHERE quantity <= 0')
            await db.execute('UPDATE characters SET gold = gold + ? WHERE id = ?', (total_price, character_id))
            await db.execute(
                """
                INSERT INTO transactions(character_id, type, amount, item_id, note, created_at)
                VALUES (?, 'sell', ?, ?, ?, ?)
                """,
                (character_id, quantity, item_id, f'Sold for {total_price} gold', now_iso()),
            )
            await db.commit()
            return True, f'Продано: {row["name"]} ×{quantity}. Получено {total_price} монет.'

    async def transfer_gold(self, sender_id: int, recipient_id: int, amount: int) -> tuple[bool, str]:
        if amount <= 0:
            return False, 'Количество монет должно быть больше 0.'
        if sender_id == recipient_id:
            return False, 'Нельзя передать монеты самому себе.'

        async with self.connect() as db:
            sender_cursor = await db.execute('SELECT * FROM characters WHERE id = ?', (sender_id,))
            sender = await sender_cursor.fetchone()
            recipient_cursor = await db.execute('SELECT * FROM characters WHERE id = ?', (recipient_id,))
            recipient = await recipient_cursor.fetchone()
            if sender is None or recipient is None:
                return False, 'Персонаж не найден.'
            if int(sender['gold']) < amount:
                return False, f'Не хватает монет. У тебя {sender["gold"]} 🪙.'

            await db.execute('UPDATE characters SET gold = gold - ? WHERE id = ?', (amount, sender_id))
            await db.execute('UPDATE characters SET gold = gold + ? WHERE id = ?', (amount, recipient_id))
            await db.execute(
                """
                INSERT INTO transactions(character_id, type, amount, note, created_at)
                VALUES (?, 'transfer_gold_out', ?, ?, ?)
                """,
                (sender_id, amount, f'To character #{recipient_id}', now_iso()),
            )
            await db.execute(
                """
                INSERT INTO transactions(character_id, type, amount, note, created_at)
                VALUES (?, 'transfer_gold_in', ?, ?, ?)
                """,
                (recipient_id, amount, f'From character #{sender_id}', now_iso()),
            )
            await db.commit()
            return True, f'Передано {amount} 🪙 персонажу {recipient["display_name"]}.'

    async def transfer_item(self, sender_id: int, recipient_id: int, item_id: int, quantity: int) -> tuple[bool, str]:
        if quantity <= 0:
            return False, 'Количество предметов должно быть больше 0.'
        if sender_id == recipient_id:
            return False, 'Нельзя передать предмет самому себе.'

        async with self.connect() as db:
            sender_item_cursor = await db.execute(
                """
                SELECT i.quantity, si.name
                FROM inventory i
                JOIN shop_items si ON si.id = i.item_id
                WHERE i.character_id = ? AND i.item_id = ?
                """,
                (sender_id, item_id),
            )
            sender_item = await sender_item_cursor.fetchone()
            if sender_item is None or int(sender_item['quantity']) <= 0:
                return False, 'Такого предмета нет в инвентаре.'
            if int(sender_item['quantity']) < quantity:
                return False, f'У тебя есть только {sender_item["quantity"]} шт.'

            recipient_cursor = await db.execute('SELECT * FROM characters WHERE id = ?', (recipient_id,))
            recipient = await recipient_cursor.fetchone()
            if recipient is None:
                return False, 'Получатель не найден.'

            await db.execute(
                'UPDATE inventory SET quantity = quantity - ? WHERE character_id = ? AND item_id = ?',
                (quantity, sender_id, item_id),
            )
            await db.execute('DELETE FROM inventory WHERE quantity <= 0')
            await db.execute(
                """
                INSERT INTO inventory(character_id, item_id, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(character_id, item_id)
                DO UPDATE SET quantity = inventory.quantity + excluded.quantity
                """,
                (recipient_id, item_id, quantity),
            )
            await db.execute(
                """
                INSERT INTO transactions(character_id, type, amount, item_id, note, created_at)
                VALUES (?, 'transfer_item_out', ?, ?, ?, ?)
                """,
                (sender_id, quantity, item_id, f'To character #{recipient_id}', now_iso()),
            )
            await db.execute(
                """
                INSERT INTO transactions(character_id, type, amount, item_id, note, created_at)
                VALUES (?, 'transfer_item_in', ?, ?, ?, ?)
                """,
                (recipient_id, quantity, item_id, f'From character #{sender_id}', now_iso()),
            )
            await db.commit()
            return True, f'Передано: {sender_item["name"]} ×{quantity} персонажу {recipient["display_name"]}.'

    async def create_quest(
        self,
        title: str,
        description: str,
        xp_reward: int,
        gold_reward: int,
        item_id: int | None = None,
        item_quantity: int = 0,
    ) -> int:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO quests(title, description, xp_reward, gold_reward, item_id, item_quantity, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title.strip(),
                    description.strip(),
                    max(0, xp_reward),
                    max(0, gold_reward),
                    item_id,
                    max(0, item_quantity),
                    now_iso(),
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def list_quests(self, only_active: bool = True) -> list[dict[str, Any]]:
        query = """
            SELECT q.*, si.name AS item_name
            FROM quests q
            LEFT JOIN shop_items si ON si.id = q.item_id
        """
        if only_active:
            query += ' WHERE q.is_active = 1'
        query += ' ORDER BY q.created_at DESC, q.title COLLATE NOCASE ASC'
        async with self.connect() as db:
            cursor = await db.execute(query)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_quest(self, quest_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT q.*, si.name AS item_name
                FROM quests q
                LEFT JOIN shop_items si ON si.id = q.item_id
                WHERE q.id = ?
                """,
                (quest_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_quest_active(self, quest_id: int, is_active: bool) -> None:
        async with self.connect() as db:
            await db.execute('UPDATE quests SET is_active = ? WHERE id = ?', (1 if is_active else 0, quest_id))
            await db.commit()

    async def award_quest(self, quest_id: int, character_ids: list[int], admin_telegram_id: int | None = None) -> tuple[bool, str]:
        character_ids = list(dict.fromkeys(character_ids))
        if not character_ids:
            return False, 'Нужно выбрать хотя бы одного персонажа.'

        async with self.connect() as db:
            quest_cursor = await db.execute('SELECT * FROM quests WHERE id = ?', (quest_id,))
            quest = await quest_cursor.fetchone()
            if quest is None:
                return False, 'Квест не найден.'

            characters_cursor = await db.execute(
                f'SELECT * FROM characters WHERE id IN ({",".join("?" for _ in character_ids)})',
                tuple(character_ids),
            )
            characters = await characters_cursor.fetchall()
            if not characters:
                return False, 'Выбранные персонажи не найдены.'

            count = len(characters)
            xp_each = (int(quest['xp_reward']) + count - 1) // count if int(quest['xp_reward']) > 0 else 0
            gold_each = (int(quest['gold_reward']) + count - 1) // count if int(quest['gold_reward']) > 0 else 0
            item_each = (int(quest['item_quantity']) + count - 1) // count if quest['item_id'] and int(quest['item_quantity']) > 0 else 0

            for character in characters:
                character_id = int(character['id'])
                if xp_each:
                    await db.execute('UPDATE characters SET xp = xp + ? WHERE id = ?', (xp_each, character_id))
                    await db.execute(
                        """
                        INSERT INTO transactions(character_id, admin_telegram_id, type, amount, note, created_at)
                        VALUES (?, ?, 'quest_xp', ?, ?, ?)
                        """,
                        (character_id, admin_telegram_id, xp_each, f'Quest #{quest_id}: {quest["title"]}', now_iso()),
                    )
                if gold_each:
                    await db.execute('UPDATE characters SET gold = gold + ? WHERE id = ?', (gold_each, character_id))
                    await db.execute(
                        """
                        INSERT INTO transactions(character_id, admin_telegram_id, type, amount, note, created_at)
                        VALUES (?, ?, 'quest_gold', ?, ?, ?)
                        """,
                        (character_id, admin_telegram_id, gold_each, f'Quest #{quest_id}: {quest["title"]}', now_iso()),
                    )
                if item_each:
                    await db.execute(
                        """
                        INSERT INTO inventory(character_id, item_id, quantity)
                        VALUES (?, ?, ?)
                        ON CONFLICT(character_id, item_id)
                        DO UPDATE SET quantity = inventory.quantity + excluded.quantity
                        """,
                        (character_id, int(quest['item_id']), item_each),
                    )
                    await db.execute(
                        """
                        INSERT INTO transactions(character_id, admin_telegram_id, type, amount, item_id, note, created_at)
                        VALUES (?, ?, 'quest_item', ?, ?, ?, ?)
                        """,
                        (character_id, admin_telegram_id, item_each, int(quest['item_id']), f'Quest #{quest_id}: {quest["title"]}', now_iso()),
                    )
            await db.commit()

            names = ', '.join(character['display_name'] for character in characters)
            parts = []
            if xp_each:
                parts.append(f'{xp_each} XP каждому')
            if gold_each:
                parts.append(f'{gold_each} 🪙 каждому')
            if item_each:
                parts.append(f'предмет ×{item_each} каждому')
            reward_text = ', '.join(parts) if parts else 'награда без XP/монет/предметов'
            return True, f'Награда за квест «{quest["title"]}» выдана: {reward_text}.\nПолучатели: {names}'

    async def roll_random_loot(self, character_id: int, admin_telegram_id: int | None = None) -> tuple[bool, str]:
        async with self.connect() as db:
            character_cursor = await db.execute('SELECT * FROM characters WHERE id = ?', (character_id,))
            character = await character_cursor.fetchone()
            if character is None:
                return False, 'Персонаж не найден.'

            loot_cursor = await db.execute(
                'SELECT * FROM shop_items WHERE loot_chance_percent > 0 ORDER BY loot_chance_percent DESC, name COLLATE NOCASE ASC'
            )
            loot_items = await loot_cursor.fetchall()
            if not loot_items:
                return False, 'Таблица рандомного лута пустая. Укажи шанс лута хотя бы у одного предмета.'

            won_items = []
            rolls = []
            for item in loot_items:
                chance = int(item['loot_chance_percent'])
                roll = random.randint(1, 100)
                rolls.append(f'{item["name"]}: {roll}/{chance}')
                if roll <= chance:
                    won_items.append(item)

            for item in won_items:
                await db.execute(
                    """
                    INSERT INTO inventory(character_id, item_id, quantity)
                    VALUES (?, ?, 1)
                    ON CONFLICT(character_id, item_id)
                    DO UPDATE SET quantity = inventory.quantity + 1
                    """,
                    (character_id, int(item['id'])),
                )
                await db.execute(
                    """
                    INSERT INTO transactions(character_id, admin_telegram_id, type, amount, item_id, note, created_at)
                    VALUES (?, ?, 'random_loot', 1, ?, ?, ?)
                    """,
                    (character_id, admin_telegram_id, int(item['id']), f'Random loot: {item["loot_chance_percent"]}%', now_iso()),
                )
            await db.commit()

            if won_items:
                loot_text = '\n'.join(f'• {item["name"]} ×1 ({item["loot_chance_percent"]}%)' for item in won_items)
                return True, f'🎲 Рандомный лут для {character["display_name"]}:\n{loot_text}'
            return True, f'🎲 Рандомный лут для {character["display_name"]}: ничего не выпало.\n\nБроски:\n' + '\n'.join(rolls)

