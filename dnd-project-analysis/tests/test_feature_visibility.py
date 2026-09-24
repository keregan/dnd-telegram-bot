from __future__ import annotations

import unittest

from app.feature_visibility import HIDDEN_GAME_COMMANDS, is_hidden_game_callback, visible_journal_entries
from app.keyboards import (
    admin_character_manage_keyboard,
    admin_menu,
    player_profile_keyboard,
    session_details_keyboard,
)


def keyboard_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def keyboard_callbacks(markup) -> list[str]:
    return [button.callback_data or '' for row in markup.inline_keyboard for button in row]


class FeatureVisibilityTests(unittest.TestCase):
    def test_hidden_commands_are_registered(self):
        self.assertEqual(HIDDEN_GAME_COMMANDS, {'session', 'initiative', 'r', 'roll'})

    def test_old_game_callbacks_are_blocked(self):
        hidden = [
            'player:session_card', 'player:initiative', 'assistant:death:4',
            'admin:quests', 'admin:rest_session:1',
            'dice:roll:d20',
        ]
        self.assertTrue(all(is_hidden_game_callback(value) for value in hidden))
        self.assertFalse(is_hidden_game_callback('player:inventory'))
        self.assertFalse(is_hidden_game_callback('shop:list'))
        self.assertFalse(is_hidden_game_callback('admin:sessions'))
        self.assertFalse(is_hidden_game_callback('admin:session:4'))
        self.assertFalse(is_hidden_game_callback('admin:quick_reward_session:4'))

    def test_player_profile_has_no_game_controls(self):
        markup = player_profile_keyboard({'id': 1, 'session_id': 2, 'inspiration': 1})
        self.assertEqual(keyboard_callbacks(markup), ['player:sheet', 'player:levels', 'menu:main'])

    def test_admin_menu_exposes_sessions_and_group_rewards(self):
        text = ' '.join(keyboard_texts(admin_menu())).lower()
        self.assertIn('сесс', text)
        self.assertIn('наград', text)
        self.assertNotIn('квест', text)

    def test_session_card_only_exposes_lightweight_admin_actions(self):
        markup = session_details_keyboard(4)
        callbacks = keyboard_callbacks(markup)
        text = ' '.join(keyboard_texts(markup)).lower()
        self.assertIn('xp и золото', text)
        self.assertIn('персонажа', text)
        self.assertTrue(all(not is_hidden_game_callback(value) for value in callbacks))
        for hidden in ('инициат', 'состояние', 'отдых', 'зацепк'):
            self.assertNotIn(hidden, text)

    def test_admin_character_has_no_hidden_game_controls(self):
        markup = admin_character_manage_keyboard({'id': 7, 'hp': 0, 'inspiration': 1})
        text = ' '.join(keyboard_texts(markup)).lower()
        for hidden in ('hp', 'инициат', 'состоян', 'спасброс', 'вдохнов', 'сесс'):
            self.assertNotIn(hidden, text)

    def test_game_entries_are_hidden_from_journal(self):
        entries = [
            {'event_type': 'short_rest', 'title': 'Отдых'},
            {'event_type': 'buy', 'title': 'Покупка'},
        ]
        self.assertEqual(visible_journal_entries(entries), [entries[1]])


if __name__ == '__main__':
    unittest.main()
