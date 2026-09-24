from __future__ import annotations


HIDDEN_GAME_COMMANDS = frozenset({'session', 'initiative', 'r', 'roll'})

HIDDEN_GAME_CALLBACK_PREFIXES = (
    'player:session_card',
    'player:spend_inspiration',
    'player:initiative',
    'dice:',
    'assistant:rsvp:',
    'assistant:brief',
    'assistant:clues',
    'assistant:loot_',
    'assistant:attendance_admin:',
    'assistant:death:',
    'assistant:death_update:',
    'assistant:condition_duration:',
    'admin:session_card:',
    'admin:session_summary:',
    'admin:initiative_',
    'admin:session_notifications',
    'admin:notify_session:',
    'admin:toggle_inspiration:',
    'admin:conditions:',
    'admin:condition_toggle:',
    'admin:rewards_menu',
    'admin:quests',
    'admin:quest',
    'admin:create_quest',
    'admin:rests',
    'admin:rest_',
    'admin:random_loot',
    'admin:set_loot_chance:',
    'admin:edit_character:hp:',
    'admin:edit_character:max_hp:',
    'admin:edit_character:initiative_bonus:',
    'admin:edit_item:heal_hp:',
)

HIDDEN_GAME_MESSAGE = 'Этот игровой раздел сейчас скрыт.'

HIDDEN_JOURNAL_TYPES = frozenset({
    'condition_added', 'condition_removed', 'inspiration', 'inspiration_spent',
    'session_changed', 'short_rest', 'long_rest', 'quick_reward',
    'quest_reward', 'random_loot', 'group_loot', 'death_save',
})


def is_hidden_game_callback(callback_data: str | None) -> bool:
    value = str(callback_data or '')
    return any(value.startswith(prefix) for prefix in HIDDEN_GAME_CALLBACK_PREFIXES)


def visible_journal_entries(entries: list[dict]) -> list[dict]:
    return [entry for entry in entries if str(entry.get('event_type') or '') not in HIDDEN_JOURNAL_TYPES]
