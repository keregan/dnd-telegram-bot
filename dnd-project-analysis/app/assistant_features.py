from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiosqlite


def feature_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class AssistantFeaturesMixin:
    async def _init_assistant_features(self, db: aiosqlite.Connection) -> None:
        await self._ensure_column(db, 'characters', 'death_save_successes', 'death_save_successes INTEGER NOT NULL DEFAULT 0')
        await self._ensure_column(db, 'characters', 'death_save_failures', 'death_save_failures INTEGER NOT NULL DEFAULT 0')
        await self._ensure_column(db, 'character_conditions', 'duration_kind', "duration_kind TEXT NOT NULL DEFAULT 'manual'")
        await self._ensure_column(db, 'character_conditions', 'remaining', 'remaining INTEGER')
        await self._ensure_column(db, 'transactions', 'reverted_at', 'reverted_at TEXT')
        await self._ensure_column(db, 'transactions', 'reverted_by', 'reverted_by INTEGER')
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS session_attendance (
                session_id INTEGER NOT NULL,
                character_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (session_id, character_id),
                FOREIGN KEY (session_id) REFERENCES game_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS campaign_clues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES game_sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS loot_bundles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES game_sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS loot_bundle_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bundle_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                assigned_character_id INTEGER,
                assigned_at TEXT,
                FOREIGN KEY (bundle_id) REFERENCES loot_bundles(id) ON DELETE CASCADE,
                FOREIGN KEY (item_id) REFERENCES shop_items(id) ON DELETE CASCADE,
                FOREIGN KEY (assigned_character_id) REFERENCES characters(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_attendance_session ON session_attendance(session_id, status);
            CREATE INDEX IF NOT EXISTS idx_clues_session ON campaign_clues(session_id, id);
            CREATE INDEX IF NOT EXISTS idx_loot_bundle_session ON loot_bundles(session_id, is_active);
            CREATE INDEX IF NOT EXISTS idx_transactions_recent ON transactions(created_at DESC, id DESC);
            """
        )

    async def search_items_for_player(
        self,
        character_id: int,
        query: str = '',
        item_filter: str = 'all',
        inventory_only: bool = False,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        clean_query = str(query or '').strip()[:80]
        params: list[Any] = []
        if inventory_only:
            sql = """
                SELECT si.*, i.quantity,
                       CASE WHEN ce.item_id IS NULL THEN 0 ELSE 1 END AS is_equipped,
                       COALESCE(ic.title, si.category, '📦 Другое') AS category_title
                FROM inventory i
                JOIN shop_items si ON si.id = i.item_id
                LEFT JOIN item_categories ic ON ic.value = COALESCE(si.category, 'other')
                LEFT JOIN character_equipment ce
                    ON ce.character_id = i.character_id AND ce.item_id = i.item_id
                WHERE i.character_id = ? AND i.quantity > 0
            """
            params.append(int(character_id))
        else:
            sql = """
                SELECT si.*, COALESCE(ic.title, si.category, '📦 Другое') AS category_title
                FROM shop_items si
                LEFT JOIN item_categories ic ON ic.value = COALESCE(si.category, 'other')
                WHERE si.is_active = 1 AND si.shop_quantity != 0
            """
        if clean_query and clean_query != '*':
            sql += ' AND (lower(si.name) LIKE lower(?) OR lower(si.description) LIKE lower(?))'
            pattern = f'%{clean_query}%'
            params.extend([pattern, pattern])
        if item_filter == 'consumable':
            sql += ' AND si.is_consumable = 1'
        elif item_filter == 'equipment':
            sql += " AND COALESCE(si.equipment_slot, '') != ''"
        elif item_filter == 'affordable' and not inventory_only:
            sql += ' AND si.price <= COALESCE((SELECT gold FROM characters WHERE id = ?), 0)'
            params.append(int(character_id))
        sql += ' ORDER BY si.name COLLATE NOCASE ASC LIMIT ?'
        params.append(max(1, min(50, int(limit))))
        async with self.connect() as db:
            rows = await (await db.execute(sql, tuple(params))).fetchall()
            return [dict(row) for row in rows]

    async def set_session_attendance(self, character_id: int, status: str) -> tuple[bool, str]:
        labels = {'yes': 'Буду', 'maybe': 'Не уверен', 'no': 'Не смогу'}
        if status not in labels:
            return False, 'Неизвестный ответ.'
        async with self.connect() as db:
            row = await (
                await db.execute('SELECT session_id FROM characters WHERE id = ?', (int(character_id),))
            ).fetchone()
            if row is None or row['session_id'] is None:
                return False, 'Персонаж не состоит в сессии.'
            await db.execute(
                """
                INSERT INTO session_attendance(session_id, character_id, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, character_id)
                DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
                """,
                (int(row['session_id']), int(character_id), status, feature_now_iso()),
            )
            await db.commit()
        return True, f'Ответ сохранён: {labels[status]}.'

    async def get_session_attendance(self, session_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (
                await db.execute(
                    """
                    SELECT c.id AS character_id, c.display_name,
                           COALESCE(sa.status, 'unknown') AS status, sa.updated_at
                    FROM characters c
                    LEFT JOIN session_attendance sa
                        ON sa.session_id = c.session_id AND sa.character_id = c.id
                    WHERE c.session_id = ?
                    ORDER BY c.display_name COLLATE NOCASE
                    """,
                    (int(session_id),),
                )
            ).fetchall()
            return [dict(row) for row in rows]

    async def get_character_attendance(self, character_id: int) -> str:
        async with self.connect() as db:
            row = await (
                await db.execute(
                    """
                    SELECT COALESCE(sa.status, 'unknown') AS status
                    FROM characters c
                    LEFT JOIN session_attendance sa
                        ON sa.session_id = c.session_id AND sa.character_id = c.id
                    WHERE c.id = ?
                    """,
                    (int(character_id),),
                )
            ).fetchone()
            return str(row['status']) if row else 'unknown'

    async def list_campaign_clues(self, session_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (
                await db.execute(
                    'SELECT * FROM campaign_clues WHERE session_id = ? ORDER BY id ASC LIMIT 5',
                    (int(session_id),),
                )
            ).fetchall()
            return [dict(row) for row in rows]

    async def add_campaign_clue(self, session_id: int, title: str, details: str = '') -> tuple[bool, str]:
        clean_title = str(title or '').strip()[:120]
        clean_details = str(details or '').strip()[:1000]
        if not clean_title:
            return False, 'Название зацепки не может быть пустым.'
        async with self.connect() as db:
            count = int((await (await db.execute(
                'SELECT COUNT(*) FROM campaign_clues WHERE session_id = ?', (int(session_id),)
            )).fetchone())[0])
            if count >= 5:
                return False, 'В сессии уже есть 5 зацепок. Удали одну перед добавлением.'
            await db.execute(
                'INSERT INTO campaign_clues(session_id, title, details, created_at) VALUES (?, ?, ?, ?)',
                (int(session_id), clean_title, clean_details, feature_now_iso()),
            )
            await db.commit()
        return True, 'Зацепка добавлена.'

    async def delete_campaign_clue(self, clue_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute('DELETE FROM campaign_clues WHERE id = ?', (int(clue_id),))
            await db.commit()
            return int(cursor.rowcount or 0) > 0

    async def create_group_loot(self, session_id: int, count: int = 3) -> tuple[bool, str, int | None]:
        amount = max(1, min(5, int(count)))
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            session = await (await db.execute('SELECT title FROM game_sessions WHERE id = ?', (int(session_id),))).fetchone()
            if session is None:
                return False, 'Сессия не найдена.', None
            rows = await (
                await db.execute(
                    """
                    SELECT id FROM shop_items
                    WHERE is_active = 1 AND shop_quantity != 0 AND loot_chance_percent > 0
                    ORDER BY RANDOM() LIMIT ?
                    """,
                    (amount,),
                )
            ).fetchall()
            if not rows:
                rows = await (
                    await db.execute(
                        'SELECT id FROM shop_items WHERE is_active = 1 AND shop_quantity != 0 ORDER BY RANDOM() LIMIT ?',
                        (amount,),
                    )
                ).fetchall()
            if not rows:
                return False, 'В магазине нет предметов для добычи.', None
            await db.execute('UPDATE loot_bundles SET is_active = 0 WHERE session_id = ? AND is_active = 1', (int(session_id),))
            cursor = await db.execute(
                'INSERT INTO loot_bundles(session_id, is_active, created_at) VALUES (?, 1, ?)',
                (int(session_id), feature_now_iso()),
            )
            bundle_id = int(cursor.lastrowid)
            await db.executemany(
                'INSERT INTO loot_bundle_items(bundle_id, item_id) VALUES (?, ?)',
                [(bundle_id, int(row['id'])) for row in rows],
            )
            await db.commit()
        return True, f'Создан набор групповой добычи: {len(rows)} предмета.', bundle_id

    async def get_active_group_loot(self, session_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            bundle = await (
                await db.execute(
                    'SELECT * FROM loot_bundles WHERE session_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1',
                    (int(session_id),),
                )
            ).fetchone()
            if bundle is None:
                return None
            rows = await (
                await db.execute(
                    """
                    SELECT lbi.id, lbi.item_id, lbi.assigned_character_id, lbi.assigned_at,
                           si.name, si.rarity, si.image_file_id, c.display_name AS assigned_name
                    FROM loot_bundle_items lbi
                    JOIN shop_items si ON si.id = lbi.item_id
                    LEFT JOIN characters c ON c.id = lbi.assigned_character_id
                    WHERE lbi.bundle_id = ? ORDER BY lbi.id
                    """,
                    (int(bundle['id']),),
                )
            ).fetchall()
            result = dict(bundle)
            result['items'] = [dict(row) for row in rows]
            return result

    async def assign_group_loot_item(
        self,
        loot_item_id: int,
        character_id: int,
        admin_telegram_id: int | None = None,
    ) -> tuple[bool, str]:
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            row = await (
                await db.execute(
                    """
                    SELECT lbi.item_id, lbi.assigned_character_id, lb.session_id,
                           si.name, c.display_name
                    FROM loot_bundle_items lbi
                    JOIN loot_bundles lb ON lb.id = lbi.bundle_id AND lb.is_active = 1
                    JOIN shop_items si ON si.id = lbi.item_id
                    JOIN characters c ON c.id = ? AND c.session_id = lb.session_id
                    WHERE lbi.id = ?
                    """,
                    (int(character_id), int(loot_item_id)),
                )
            ).fetchone()
            if row is None:
                return False, 'Предмет или персонаж не найден в этой сессии.'
            if row['assigned_character_id'] is not None:
                return False, 'Этот предмет уже распределён.'
            cursor = await db.execute(
                'UPDATE loot_bundle_items SET assigned_character_id = ?, assigned_at = ? WHERE id = ? AND assigned_character_id IS NULL',
                (int(character_id), feature_now_iso(), int(loot_item_id)),
            )
            if int(cursor.rowcount or 0) <= 0:
                return False, 'Предмет уже распределён другим действием.'
            await db.execute(
                """
                INSERT INTO inventory(character_id, item_id, quantity) VALUES (?, ?, 1)
                ON CONFLICT(character_id, item_id) DO UPDATE SET quantity = quantity + 1
                """,
                (int(character_id), int(row['item_id'])),
            )
            await db.execute(
                """
                INSERT INTO transactions(character_id, admin_telegram_id, type, amount, item_id, note, created_at)
                VALUES (?, ?, 'group_loot', 1, ?, 'Group loot assigned', ?)
                """,
                (int(character_id), admin_telegram_id, int(row['item_id']), feature_now_iso()),
            )
            await self._add_journal_entry(
                db, int(character_id), 'group_loot', 'Групповая добыча',
                f'Получено: {row["name"]} ×1.', admin_telegram_id,
            )
            await db.commit()
            return True, f'{row["name"]} передан персонажу {row["display_name"]}.'

    async def update_death_save(self, character_id: int, result: str) -> tuple[bool, str]:
        if result not in {'success', 'failure', 'reset'}:
            return False, 'Неизвестный результат спасброска.'
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            row = await (
                await db.execute(
                    'SELECT display_name, hp, death_save_successes, death_save_failures FROM characters WHERE id = ?',
                    (int(character_id),),
                )
            ).fetchone()
            if row is None:
                return False, 'Персонаж не найден.'
            if result != 'reset' and int(row['hp'] or 0) > 0:
                return False, 'Спасброски доступны только при 0 HP.'
            success = int(row['death_save_successes'] or 0)
            failure = int(row['death_save_failures'] or 0)
            if result == 'reset':
                success = failure = 0
            elif result == 'success':
                success = min(3, success + 1)
            else:
                failure = min(3, failure + 1)
            await db.execute(
                'UPDATE characters SET death_save_successes = ?, death_save_failures = ? WHERE id = ?',
                (success, failure, int(character_id)),
            )
            await self._add_journal_entry(
                db, int(character_id), 'death_save', 'Спасбросок от смерти',
                f'Успехи: {success}/3. Провалы: {failure}/3.',
            )
            await db.commit()
        state = 'стабилизирован' if success >= 3 else 'погиб' if failure >= 3 else 'борется за жизнь'
        return True, f'{row["display_name"]}: успехи {success}/3, провалы {failure}/3 — {state}.'

    async def set_condition_duration(
        self,
        character_id: int,
        condition: str,
        duration_kind: str,
        remaining: int | None = None,
    ) -> tuple[bool, str]:
        if duration_kind not in {'manual', 'turns', 'rounds', 'rest'}:
            return False, 'Неизвестная длительность.'
        clean_remaining = None if duration_kind in {'manual', 'rest'} else max(1, int(remaining or 1))
        async with self.connect() as db:
            cursor = await db.execute(
                """
                UPDATE character_conditions SET duration_kind = ?, remaining = ?
                WHERE character_id = ? AND condition = ?
                """,
                (duration_kind, clean_remaining, int(character_id), str(condition)),
            )
            await db.commit()
            if int(cursor.rowcount or 0) <= 0:
                return False, 'Состояние не найдено.'
        return True, 'Длительность состояния обновлена.'

    async def list_character_condition_details(self, character_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (
                await db.execute(
                    """
                    SELECT condition, duration_kind, remaining, added_at
                    FROM character_conditions WHERE character_id = ? ORDER BY condition
                    """,
                    (int(character_id),),
                )
            ).fetchall()
            return [dict(row) for row in rows]

    async def _tick_temporary_conditions(self, db: aiosqlite.Connection, kind: str) -> list[tuple[int, str]]:
        await db.execute(
            """
            UPDATE character_conditions
            SET remaining = remaining - 1
            WHERE duration_kind = ? AND remaining IS NOT NULL AND remaining > 0
            """,
            (kind,),
        )
        rows = await (
            await db.execute(
                'SELECT character_id, condition FROM character_conditions WHERE duration_kind = ? AND remaining <= 0',
                (kind,),
            )
        ).fetchall()
        await db.execute(
            'DELETE FROM character_conditions WHERE duration_kind = ? AND remaining <= 0',
            (kind,),
        )
        return [(int(row['character_id']), str(row['condition'])) for row in rows]

    async def list_recent_admin_transactions(self, limit: int = 15) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (
                await db.execute(
                    """
                    SELECT t.*, c.display_name, si.name AS item_name
                    FROM transactions t
                    LEFT JOIN characters c ON c.id = t.character_id
                    LEFT JOIN shop_items si ON si.id = t.item_id
                    WHERE t.admin_telegram_id IS NOT NULL
                    ORDER BY t.id DESC LIMIT ?
                    """,
                    (max(1, min(50, int(limit))),),
                )
            ).fetchall()
            return [dict(row) for row in rows]

    async def undo_admin_transaction(self, transaction_id: int, admin_telegram_id: int) -> tuple[bool, str]:
        xp_types = {'xp', 'quick_reward_xp'}
        gold_types = {'gold', 'quick_reward_gold'}
        item_types = {'item', 'random_loot', 'group_loot'}
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            row = await (
                await db.execute(
                    """
                    SELECT t.*, c.display_name, si.name AS item_name
                    FROM transactions t
                    LEFT JOIN characters c ON c.id = t.character_id
                    LEFT JOIN shop_items si ON si.id = t.item_id
                    WHERE t.id = ?
                    """,
                    (int(transaction_id),),
                )
            ).fetchone()
            if row is None:
                return False, 'Операция не найдена.'
            if row['reverted_at']:
                return False, 'Эта операция уже отменена.'
            tx_type = str(row['type'])
            amount = int(row['amount'] or 0)
            character_id = row['character_id']
            if character_id is None:
                return False, 'У операции нет персонажа.'
            if tx_type in xp_types | gold_types and amount <= 0:
                return False, 'Автоматически отменяются только положительные награды.'
            if tx_type in xp_types:
                current = int((await (await db.execute('SELECT xp FROM characters WHERE id = ?', (character_id,))).fetchone())[0])
                if current - amount < 0:
                    return False, 'Нельзя отменить: XP уже меньше выданного количества.'
                await db.execute('UPDATE characters SET xp = xp - ? WHERE id = ?', (amount, character_id))
                description = f'XP {amount:+d}'
            elif tx_type in gold_types:
                current = int((await (await db.execute('SELECT gold FROM characters WHERE id = ?', (character_id,))).fetchone())[0])
                if current - amount < 0:
                    return False, 'Нельзя отменить: монет уже меньше выданного количества.'
                await db.execute('UPDATE characters SET gold = gold - ? WHERE id = ?', (amount, character_id))
                description = f'монеты {amount:+d}'
            elif tx_type in item_types and row['item_id'] is not None:
                if amount > 0:
                    inventory = await (
                        await db.execute(
                            'SELECT quantity FROM inventory WHERE character_id = ? AND item_id = ?',
                            (character_id, row['item_id']),
                        )
                    ).fetchone()
                    if inventory is None or int(inventory['quantity']) < amount:
                        return False, 'Нельзя отменить: предметов уже недостаточно.'
                await db.execute(
                    """
                    INSERT INTO inventory(character_id, item_id, quantity) VALUES (?, ?, ?)
                    ON CONFLICT(character_id, item_id) DO UPDATE SET quantity = inventory.quantity + excluded.quantity
                    """,
                    (character_id, row['item_id'], -amount),
                )
                await db.execute('DELETE FROM inventory WHERE quantity <= 0')
                await self._cleanup_equipment_without_inventory(db)
                description = f'{row["item_name"] or "предмет"} ×{amount:+d}'
            else:
                return False, 'Эту операцию нельзя безопасно отменить автоматически.'
            await db.execute(
                'UPDATE transactions SET reverted_at = ?, reverted_by = ? WHERE id = ?',
                (feature_now_iso(), int(admin_telegram_id), int(transaction_id)),
            )
            await self._add_journal_entry(
                db, int(character_id), 'admin_undo', 'Операция мастера отменена',
                f'Отменена операция #{transaction_id}: {description}.', int(admin_telegram_id),
            )
            await db.commit()
            return True, f'Операция #{transaction_id} отменена для {row["display_name"] or "персонажа"}.'
