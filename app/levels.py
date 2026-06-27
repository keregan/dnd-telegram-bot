from __future__ import annotations

from typing import Any


# Таблица опыта DnD 5e: уровень, минимальный XP для уровня, бонус владения.
LEVEL_TABLE: list[dict[str, int]] = [
    {'level': 1, 'xp': 0, 'proficiency_bonus': 2},
    {'level': 2, 'xp': 300, 'proficiency_bonus': 2},
    {'level': 3, 'xp': 900, 'proficiency_bonus': 2},
    {'level': 4, 'xp': 2700, 'proficiency_bonus': 2},
    {'level': 5, 'xp': 6500, 'proficiency_bonus': 3},
    {'level': 6, 'xp': 14000, 'proficiency_bonus': 3},
    {'level': 7, 'xp': 23000, 'proficiency_bonus': 3},
    {'level': 8, 'xp': 34000, 'proficiency_bonus': 3},
    {'level': 9, 'xp': 48000, 'proficiency_bonus': 4},
    {'level': 10, 'xp': 64000, 'proficiency_bonus': 4},
    {'level': 11, 'xp': 85000, 'proficiency_bonus': 4},
    {'level': 12, 'xp': 100000, 'proficiency_bonus': 4},
    {'level': 13, 'xp': 120000, 'proficiency_bonus': 5},
    {'level': 14, 'xp': 140000, 'proficiency_bonus': 5},
    {'level': 15, 'xp': 165000, 'proficiency_bonus': 5},
    {'level': 16, 'xp': 195000, 'proficiency_bonus': 5},
    {'level': 17, 'xp': 225000, 'proficiency_bonus': 6},
    {'level': 18, 'xp': 265000, 'proficiency_bonus': 6},
    {'level': 19, 'xp': 305000, 'proficiency_bonus': 6},
    {'level': 20, 'xp': 355000, 'proficiency_bonus': 6},
]


def get_level_info(xp: int) -> dict[str, int | None]:
    """Return DnD level info for a character XP value.

    Level is not stored separately in DB. It is calculated from XP so it never
    gets out of sync when the admin adds/removes experience or awards quests.
    """
    xp = max(0, int(xp))
    current = LEVEL_TABLE[0]
    next_row: dict[str, int] | None = None

    for index, row in enumerate(LEVEL_TABLE):
        if xp >= row['xp']:
            current = row
            next_row = LEVEL_TABLE[index + 1] if index + 1 < len(LEVEL_TABLE) else None
        else:
            break

    current_level_xp = int(current['xp'])
    next_level_xp = int(next_row['xp']) if next_row else None
    xp_to_next = max(0, next_level_xp - xp) if next_level_xp is not None else 0
    xp_in_level = xp - current_level_xp
    level_span = (next_level_xp - current_level_xp) if next_level_xp is not None else 0

    return {
        'level': int(current['level']),
        'proficiency_bonus': int(current['proficiency_bonus']),
        'current_level_xp': current_level_xp,
        'next_level_xp': next_level_xp,
        'xp_to_next_level': xp_to_next,
        'xp_in_current_level': xp_in_level,
        'xp_for_current_level_span': level_span,
    }


def enrich_character(character: dict[str, Any]) -> dict[str, Any]:
    """Add calculated level fields to a character dictionary."""
    result = dict(character)
    result.update(get_level_info(int(result.get('xp', 0))))
    return result


def level_progress_text(character: dict[str, Any]) -> str:
    level = int(character['level'])
    xp = int(character['xp'])
    bonus = int(character['proficiency_bonus'])
    next_level_xp = character.get('next_level_xp')

    if next_level_xp is None:
        return (
            f'Уровень: <b>{level}</b> / 20\n'
            f'XP: <b>{xp}</b>\n'
            f'Бонус владения: <b>+{bonus}</b>\n'
            'До следующего уровня: <b>максимальный уровень</b>'
        )

    return (
        f'Уровень: <b>{level}</b> / 20\n'
        f'XP: <b>{xp}</b> / {next_level_xp}\n'
        f'Бонус владения: <b>+{bonus}</b>\n'
        f'До следующего уровня: <b>{character["xp_to_next_level"]}</b> XP'
    )


def levels_table_text() -> str:
    lines = ['📈 <b>Таблица уровней DnD</b>', '']
    for row in LEVEL_TABLE:
        lines.append(
            f'{row["level"]}. XP: <b>{row["xp"]}</b> | бонус владения: <b>+{row["proficiency_bonus"]}</b>'
        )
    return '\n'.join(lines)
