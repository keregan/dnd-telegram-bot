import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database import (
    CHARACTER_SHOP_ITEMS,
    DATABASE_HARDENING_MIGRATION,
    GAMEPLAY_ASSISTANT_MIGRATION,
    ITEM_LOCAL_IMAGES,
    Database,
)

CHARACTER_SHOP_ITEM_NAMES = {item['name'] for item in CHARACTER_SHOP_ITEMS}


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temp_dir.name) / 'test.sqlite3')
        self.db = Database(self.database_path)
        await self.db.init()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def create_character(self, suffix: str, password: str = 'secret1') -> int:
        return await self.db.create_character(f'user_{suffix}', password, f'Hero {suffix}')

    async def test_schema_wal_migrations_and_integrity(self):
        async with self.db.connect() as connection:
            journal_mode = await (await connection.execute('PRAGMA journal_mode')).fetchone()
            integrity = await (await connection.execute('PRAGMA integrity_check')).fetchone()
            foreign_keys = await (await connection.execute('PRAGMA foreign_key_check')).fetchall()
            migrations = {
                row['name']
                for row in await (await connection.execute('SELECT name FROM app_migrations')).fetchall()
            }
            tables = {
                row['name']
                for row in await (
                    await connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                ).fetchall()
            }

        self.assertEqual(journal_mode[0], 'wal')
        self.assertEqual(integrity[0], 'ok')
        self.assertEqual(foreign_keys, [])
        self.assertIn(DATABASE_HARDENING_MIGRATION, migrations)
        self.assertIn(GAMEPLAY_ASSISTANT_MIGRATION, migrations)
        self.assertIn('auth_attempts', tables)
        self.assertIn('quest_awards', tables)
        self.assertIn('character_conditions', tables)
        self.assertIn('initiative_encounters', tables)
        self.assertIn('initiative_entries', tables)
        self.assertIn('character_sheets', tables)
        self.assertIn('character_sheet_entries', tables)

    async def test_login_rate_limit_and_password_policy(self):
        with self.assertRaises(ValueError):
            await self.db.create_character('short_password', '12345', 'Hero')

        await self.create_character('login', 'secret1')
        for _ in range(5):
            self.assertIsNone(await self.db.authenticate_character('user_login', 'wrong1', 1001))
        with self.assertRaises(PermissionError):
            await self.db.authenticate_character('user_login', 'secret1', 1001)

        character = await self.db.authenticate_character('user_login', 'secret1', 1002)
        self.assertIsNotNone(character)

    async def test_parallel_purchase_is_atomic(self):
        character_id = await self.create_character('buyer')
        await self.db.add_gold(character_id, 100)
        item_id = await self.db.create_item(
            'Тестовый меч', 'Проверка покупки', 80, 'common', 'weapon', shop_quantity=2
        )

        results = await asyncio.gather(
            self.db.buy_item(character_id, item_id, 1),
            self.db.buy_item(character_id, item_id, 1),
        )

        self.assertEqual(sum(1 for success, _ in results if success), 1)
        character = await self.db.get_character(character_id)
        item = await self.db.get_item(item_id)
        inventory = await self.db.list_inventory(character_id)
        bought = next(row for row in inventory if row['id'] == item_id)
        self.assertEqual(character['gold'], 20)
        self.assertEqual(item['shop_quantity'], 1)
        self.assertEqual(bought['quantity'], 1)

    async def test_inventory_equipment_consumables_and_sale(self):
        character_id = await self.create_character('inventory')
        bag_id = await self.db.create_item('Тестовая сумка', 'Сумка', 20, 'common', 'gear')
        potion_id = await self.db.create_item('Тестовое зелье', 'Зелье', 10, 'common', 'consumable')
        await self.db.add_item_to_inventory(character_id, bag_id, 1)
        await self.db.add_item_to_inventory(character_id, potion_id, 2)

        equipped, _ = await self.db.equip_item(character_id, bag_id)
        used, _ = await self.db.use_item(character_id, potion_id)
        sold, _ = await self.db.sell_item(character_id, potion_id, 1)
        carry = await self.db.get_character_carry_info(character_id)
        inventory = await self.db.list_inventory(character_id)

        self.assertTrue(equipped)
        self.assertTrue(used)
        self.assertTrue(sold)
        self.assertEqual(carry['carry_bonus_kg'], 10.0)
        self.assertFalse(any(row['id'] == potion_id for row in inventory))

    async def test_transfers_require_same_session_and_never_go_negative(self):
        sender_id = await self.create_character('sender')
        recipient_id = await self.create_character('recipient')
        await self.db.add_gold(sender_id, 10)

        success, _ = await self.db.transfer_gold(sender_id, recipient_id, 7)
        second_success, _ = await self.db.transfer_gold(sender_id, recipient_id, 7)
        sender = await self.db.get_character(sender_id)
        recipient = await self.db.get_character(recipient_id)

        self.assertTrue(success)
        self.assertFalse(second_success)
        self.assertEqual(sender['gold'], 3)
        self.assertEqual(recipient['gold'], 7)

        other_session = await self.db.create_session('Other session')
        await self.db.set_character_session(recipient_id, other_session)
        cross_session, _ = await self.db.transfer_gold(sender_id, recipient_id, 1)
        self.assertFalse(cross_session)

    async def test_quest_reward_is_not_duplicated_and_rest_is_journaled(self):
        first_id = await self.create_character('quest_one')
        second_id = await self.create_character('quest_two')
        quest_id = await self.db.create_quest('Test quest', '', 100, 30)

        awarded, _ = await self.db.award_quest(quest_id, [first_id, second_id], 42)
        repeated, _ = await self.db.award_quest(quest_id, [first_id, second_id], 42)
        first = await self.db.get_character(first_id)
        second = await self.db.get_character(second_id)

        self.assertTrue(awarded)
        self.assertFalse(repeated)
        self.assertEqual(first['xp'], 50)
        self.assertEqual(second['xp'], 50)
        self.assertEqual(first['gold'], 15)
        self.assertEqual(second['gold'], 15)

        await self.db.update_character_field(first_id, 'max_hp', 20)
        await self.db.update_character_field(first_id, 'hp', 5)
        session_id = first['session_id']
        rested, _ = await self.db.apply_session_rest(session_id, 'short', 4, 'Test rest', 42)
        self.assertTrue(rested)
        first = await self.db.get_character(first_id)
        self.assertEqual(first['hp'], 9)
        journal = await self.db.list_character_journal(first_id, 100)
        self.assertTrue(any(row['event_type'] == 'short_rest' for row in journal))

    async def test_legacy_schema_receives_new_columns_and_tables(self):
        legacy_path = str(Path(self.temp_dir.name) / 'legacy.sqlite3')
        connection = sqlite3.connect(legacy_path)
        connection.executescript(
            """
            CREATE TABLE characters (
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
            CREATE TABLE shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                price INTEGER NOT NULL DEFAULT 0,
                rarity TEXT NOT NULL DEFAULT 'common',
                image_file_id TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.close()

        legacy_db = Database(legacy_path)
        await legacy_db.init()
        async with legacy_db.connect() as migrated:
            character_columns = {
                row['name']
                for row in await (await migrated.execute('PRAGMA table_info(characters)')).fetchall()
            }
            item_columns = {
                row['name']
                for row in await (await migrated.execute('PRAGMA table_info(shop_items)')).fetchall()
            }
            tables = {
                row['name']
                for row in await (
                    await migrated.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                ).fetchall()
            }

        self.assertTrue({'hp', 'max_hp', 'session_id', 'admin_notes', 'inspiration', 'initiative_bonus'} <= character_columns)
        self.assertTrue({'sell_price', 'weight_kg', 'equipment_slot', 'heal_hp'} <= item_columns)
        self.assertIn('quest_awards', tables)
        self.assertIn('auth_attempts', tables)
        self.assertIn('character_conditions', tables)
        self.assertIn('initiative_encounters', tables)

    async def test_session_card_inspiration_conditions_healing_and_initiative(self):
        first_id = await self.create_character('assistant_one')
        second_id = await self.create_character('assistant_two')
        first = await self.db.get_character(first_id)
        session_id = int(first['session_id'])

        updated, _ = await self.db.update_session_card_field(session_id, 'current_goal', 'Найти старую башню')
        session = await self.db.get_session(session_id)
        self.assertTrue(updated)
        self.assertEqual(session['current_goal'], 'Найти старую башню')

        inspired, _ = await self.db.toggle_character_inspiration(first_id, 42)
        conditioned, _ = await self.db.toggle_character_condition(first_id, 'poisoned', 42)
        self.assertTrue(inspired)
        self.assertTrue(conditioned)
        self.assertEqual(await self.db.list_character_conditions(first_id), ['poisoned'])
        self.assertEqual((await self.db.get_character(first_id))['inspiration'], 1)
        spent, _ = await self.db.spend_inspiration(first_id)
        self.assertTrue(spent)

        potion_id = await self.db.create_item('Лечебное тестовое зелье', '', 10, 'common', 'consumable')
        await self.db.update_item_field(potion_id, 'heal_hp', 5)
        await self.db.add_item_to_inventory(first_id, potion_id, 1)
        await self.db.update_character_field(first_id, 'max_hp', 10)
        await self.db.update_character_field(first_id, 'hp', 3)
        used, _ = await self.db.use_item(first_id, potion_id)
        self.assertTrue(used)
        self.assertEqual((await self.db.get_character(first_id))['hp'], 8)

        await self.db.update_character_field(first_id, 'initiative_bonus', 3)
        started, _, encounter_id = await self.db.start_initiative(session_id)
        first_roll, _ = await self.db.roll_character_initiative(first_id)
        repeated_roll, _ = await self.db.roll_character_initiative(first_id)
        second_roll, _ = await self.db.roll_character_initiative(second_id)
        encounter = await self.db.get_active_initiative(session_id)
        advanced, _ = await self.db.advance_initiative(int(encounter_id))
        ended, _ = await self.db.end_initiative(int(encounter_id))

        self.assertTrue(started)
        self.assertTrue(first_roll)
        self.assertFalse(repeated_roll)
        self.assertTrue(second_roll)
        self.assertEqual(len(encounter['entries']), 2)
        self.assertTrue(advanced)
        self.assertTrue(ended)

    async def test_shop_expansion_has_complete_cards_and_catalog_corrections(self):
        expected_names = {
            'Копьё путешественника',
            'Короткий лук',
            'Посеребрённые болты ×5',
            'Лом',
            'Набор маскировки',
            'Набор травника',
            'Шарики в мешочке',
            'Калтропы',
            'Противоядие',
            'Лечебная мазь',
            'Зелье ночного зрения',
            'Пыль истинного контура',
            'Водонепроницаемый тубус',
            'Складной шест',
            'Плащ непогоды',
            'Монеты тихого разговора',
            'Мел возвращающегося пути',
            'Брошь сосредоточения',
            'Фонарь следов',
            'Колокольчик лжи',
            'Перчатки осторожного вора',
            'Компас неизбранной дороги',
            'Сапоги одолженного шага',
            'Фонарь второй тени',
            'Песочные часы малого возврата',
            'Фляга громкой тишины',
            'Нить общей удачи',
            'Мел подслушивающей двери',
            'Монета честного долга',
            'Ножны запомненной стали',
            'Осколок отложенной раны',
            'Свиток Щита',
            'Чернильница быстрого переписывания',
            'Жезл направленного воплощения',
            'Нить дальней мысли',
            'Флакон внутреннего резонанса',
            'Рубин боевого мага',
            'Двуручный меч строевого мага +1',
            'Печать драконьего дыхания',
        }
        async with self.db.connect() as connection:
            rows = await (
                await connection.execute(
                    """
                    SELECT name, description, price, sell_price, image_file_id, is_active,
                           is_consumable, equipment_slot, heal_hp
                    FROM shop_items
                    """
                )
            ).fetchall()
        items = {row['name']: row for row in rows if row['name'] in expected_names}

        self.assertEqual(set(items), expected_names)
        project_root = Path(__file__).resolve().parents[1]
        for name, item in items.items():
            self.assertTrue(str(item['description']).strip(), name)
            self.assertEqual(item['sell_price'], int(item['price'] * 0.8), name)
            self.assertEqual(item['image_file_id'], ITEM_LOCAL_IMAGES[name], name)
            self.assertTrue((project_root / item['image_file_id']).is_file(), name)

        self.assertEqual(items['Копьё путешественника']['equipment_slot'], 'weapon')
        self.assertEqual(items['Лом']['equipment_slot'], 'tool')
        self.assertEqual(items['Лечебная мазь']['is_consumable'], 1)
        self.assertEqual(items['Лечебная мазь']['heal_hp'], 6)
        self.assertEqual(items['Сапоги одолженного шага']['equipment_slot'], 'armor')
        self.assertEqual(items['Фляга громкой тишины']['is_consumable'], 1)
        self.assertEqual(items['Нить общей удачи']['equipment_slot'], 'accessory')
        self.assertEqual(items['Ножны запомненной стали']['equipment_slot'], 'gear')
        for name in {
            'Компас неизбранной дороги',
            'Песочные часы малого возврата',
            'Нить общей удачи',
            'Мел подслушивающей двери',
            'Монета честного долга',
            'Осколок отложенной раны',
            'Ножны запомненной стали',
            'Свиток Щита',
            'Чернильница быстрого переписывания',
            'Жезл направленного воплощения',
            'Нить дальней мысли',
            'Флакон внутреннего резонанса',
            'Рубин боевого мага',
            'Двуручный меч строевого мага +1',
            'Печать драконьего дыхания',
        }:
            self.assertEqual(items[name]['is_active'], 1, name)
        for name in {
            'Сапоги одолженного шага',
            'Фонарь второй тени',
            'Фляга громкой тишины',
        }:
            self.assertEqual(items[name]['is_active'], 0, name)

        async with self.db.connect() as connection:
            rows = await (
                await connection.execute(
                    """
                    SELECT name, category, shop_quantity, is_consumable, equipment_slot, weight_kg
                    FROM shop_items
                    WHERE name IN ({})
                    """.format(','.join('?' for _ in CHARACTER_SHOP_ITEM_NAMES)),
                    tuple(CHARACTER_SHOP_ITEM_NAMES),
                )
            ).fetchall()
        character_items = {row['name']: row for row in rows}
        self.assertEqual(set(character_items), CHARACTER_SHOP_ITEM_NAMES)
        for name, item in character_items.items():
            self.assertEqual(item['shop_quantity'], 2, name)
        self.assertEqual(character_items['Свиток Щита']['category'], 'consumable')
        self.assertEqual(character_items['Свиток Щита']['is_consumable'], 1)
        self.assertEqual(character_items['Чернильница быстрого переписывания']['category'], 'tools')
        self.assertEqual(character_items['Жезл направленного воплощения']['equipment_slot'], 'weapon')
        self.assertEqual(character_items['Двуручный меч строевого мага +1']['category'], 'weapon')
        self.assertEqual(character_items['Ножны запомненной стали']['category'], 'gear')

        crossbow_id = await self.db.create_item('Ручной тестовый предмет', 'Описание мастера', 20, 'common', 'consumable')
        await self.db.update_item_field(crossbow_id, 'price', 777)
        await self.db.update_item_field(crossbow_id, 'description', 'Изменено вручную')
        await self.db.init()
        crossbow = await self.db.get_item(crossbow_id)
        self.assertEqual(crossbow['price'], 777)
        self.assertEqual(crossbow['description'], 'Изменено вручную')

        await self.db.init()
        async with self.db.connect() as connection:
            duplicate_rows = await (
                await connection.execute(
                    """
                    SELECT name, COUNT(*) AS amount
                    FROM shop_items
                    WHERE name IN ({})
                    GROUP BY name
                    HAVING COUNT(*) != 1
                    """.format(','.join('?' for _ in expected_names)),
                    tuple(expected_names),
                )
            ).fetchall()
        self.assertEqual(duplicate_rows, [])


if __name__ == '__main__':
    unittest.main()
