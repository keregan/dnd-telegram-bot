import tempfile
import unittest
import sqlite3
from pathlib import Path

from app.backup_service import run_backup_once
from app.database import Database


class AssistantFeatureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = str(Path(self.temp_dir.name) / 'bot.sqlite3')
        self.db = Database(self.path)
        await self.db.init()
        self.character_id = await self.db.create_character('assistant_test', 'secret1', 'Assistant Hero')
        self.character = await self.db.get_character(self.character_id)
        self.session_id = int(self.character['session_id'])

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_attendance_clues_and_search(self):
        success, _ = await self.db.set_session_attendance(self.character_id, 'yes')
        self.assertTrue(success)
        self.assertEqual(await self.db.get_character_attendance(self.character_id), 'yes')

        for number in range(5):
            added, _ = await self.db.add_campaign_clue(self.session_id, f'Clue {number}', 'Details')
            self.assertTrue(added)
        added, _ = await self.db.add_campaign_clue(self.session_id, 'Too many')
        self.assertFalse(added)
        self.assertEqual(len(await self.db.list_campaign_clues(self.session_id)), 5)

        item_id = await self.db.create_item(
            'Searchable potion', 'Very specific description', 10, 'common',
            is_consumable=True, weight_kg=0.25, heal_hp=4,
        )
        rows = await self.db.search_items_for_player(self.character_id, 'specific', 'consumable')
        self.assertIn(item_id, {row['id'] for row in rows})
        item = await self.db.get_item(item_id)
        self.assertEqual(item['weight_kg'], 0.25)
        self.assertEqual(item['heal_hp'], 4)

    async def test_group_loot_and_undo(self):
        item_id = await self.db.create_item('Loot test item', '', 5, 'common', loot_chance_percent=100)
        created, _, _ = await self.db.create_group_loot(self.session_id, 1)
        self.assertTrue(created)
        loot = await self.db.get_active_group_loot(self.session_id)
        assigned_item_id = int(loot['items'][0]['item_id'])
        assigned, _ = await self.db.assign_group_loot_item(loot['items'][0]['id'], self.character_id, 42)
        self.assertTrue(assigned)

        transactions = await self.db.list_recent_admin_transactions()
        transaction = next(row for row in transactions if row['type'] == 'group_loot')
        undone, _ = await self.db.undo_admin_transaction(transaction['id'], 42)
        self.assertTrue(undone)
        inventory = await self.db.list_inventory(self.character_id)
        self.assertFalse(any(row['id'] == assigned_item_id for row in inventory))

    async def test_death_saves_and_temporary_conditions(self):
        await self.db.update_character_field(self.character_id, 'hp', 0)
        success, _ = await self.db.update_death_save(self.character_id, 'success')
        self.assertTrue(success)
        self.assertEqual((await self.db.get_character(self.character_id))['death_save_successes'], 1)

        await self.db.toggle_character_condition(self.character_id, 'poisoned', 42)
        duration, _ = await self.db.set_condition_duration(self.character_id, 'poisoned', 'turns', 1)
        self.assertTrue(duration)
        started, _, encounter_id = await self.db.start_initiative(self.session_id)
        self.assertTrue(started)
        await self.db.roll_character_initiative(self.character_id)
        await self.db.advance_initiative(encounter_id)
        self.assertEqual(await self.db.list_character_conditions(self.character_id), [])

        await self.db.update_character_field(self.character_id, 'hp', 5)
        character = await self.db.get_character(self.character_id)
        self.assertEqual(character['death_save_successes'], 0)
        self.assertEqual(character['death_save_failures'], 0)

    async def test_sqlite_backup_is_valid(self):
        backup_dir = str(Path(self.temp_dir.name) / 'backups')
        path = await run_backup_once(self.path, backup_dir, 14)
        self.assertTrue(path.is_file())
        with sqlite3.connect(path) as connection:
            integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
        self.assertEqual(integrity, 'ok')
        self.assertFalse(path.with_name(path.name + '-wal').exists())
        self.assertFalse(path.with_name(path.name + '-shm').exists())


if __name__ == '__main__':
    unittest.main()
