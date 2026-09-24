from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.character_sheet import parse_lss_character
from app.database import Database
from app.security import verify_password


def sample_export() -> dict:
    trait = {
        'type': 'spoiler',
        'content': [
            {'type': 'spoilerSummary', 'content': [{'type': 'text', 'text': 'Точное заклинание'}]},
            {'type': 'spoilerContent', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Полное описание.'}]}]},
        ],
    }
    data = {
        'name': {'value': 'Солар(Олег 4)'},
        'info': {
            'charClass': {'value': 'Волшебник'},
            'charSubclass': {'value': 'Воплотитель'},
            'level': {'value': 6},
            'race': {'value': 'Эладрин'},
            'background': {'value': 'Мудрец'},
            'alignment': {'value': 'Хаотично-Нейтральный'},
            'experience': {'value': 42},
        },
        'stats': {'str': {'score': 8}},
        'skills': {'arcana': {'baseStat': 'int', 'isProf': 1}},
        'text': {
            'traits': {'value': {'data': {'type': 'doc', 'content': [trait, trait]}}},
            'feats': {'value': {'data': {'type': 'doc', 'content': []}}},
            'prof': {'value': {'data': {'type': 'doc', 'content': []}}},
        },
        'coins': {'gp': {'value': 13}},
        'resources': {},
    }
    return {
        'data': json.dumps(data, ensure_ascii=False),
        'spells': {'book': ['spell-1'], 'prepared': ['spell-1'], 'granted': [], 'slotless': []},
        'wizard': {'choices': {}},
    }


class CharacterSheetParserTests(unittest.TestCase):
    def test_parser_extracts_identity_sections_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'character.json'
            path.write_text(json.dumps(sample_export(), ensure_ascii=False), encoding='utf-8')
            sheet = parse_lss_character(
                path,
                {'spell-1': {'name': 'Огненный снаряд', 'description': 'Урон огнём.', 'level': 0}},
            )

        self.assertEqual(sheet['login'], 'solar')
        self.assertEqual(sheet['player_name'], 'Олег')
        self.assertEqual(sheet['session_title'], 'Сессия 4')
        self.assertEqual(sheet['level'], 6)
        self.assertEqual(len([item for item in sheet['entries'] if item['section'] == 'ability']), 1)
        self.assertEqual(len([item for item in sheet['entries'] if item['section'] == 'skill']), 1)
        self.assertEqual(len([item for item in sheet['entries'] if item['section'] == 'cantrip']), 1)


class CharacterSheetDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / 'character.json'
        self.path.write_text(json.dumps(sample_export(), ensure_ascii=False), encoding='utf-8')
        self.db = Database(str(Path(self.temp_dir.name) / 'database.sqlite3'))
        await self.db.init()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_import_is_repeatable_and_allows_requested_temporary_password(self):
        sheet = parse_lss_character(self.path)
        first = await self.db.import_character_sheet(sheet, '12345')
        second = await self.db.import_character_sheet(sheet, '12345')

        self.assertTrue(first['created'])
        self.assertFalse(second['created'])
        self.assertEqual(first['character_id'], second['character_id'])
        character = await self.db.get_character(first['character_id'])
        imported = await self.db.get_character_sheet(first['character_id'])
        entries = await self.db.list_character_sheet_entries(first['character_id'], 'ability')
        self.assertEqual(character['session_title'], 'Сессия 4')
        self.assertEqual(imported['player_name'], 'Олег')
        self.assertEqual(len(entries), 1)
        async with self.db.connect() as connection:
            row = await (
                await connection.execute(
                    'SELECT password_salt, password_hash FROM characters WHERE id = ?',
                    (first['character_id'],),
                )
            ).fetchone()
        self.assertTrue(verify_password('12345', row['password_salt'], row['password_hash']))


if __name__ == '__main__':
    unittest.main()
