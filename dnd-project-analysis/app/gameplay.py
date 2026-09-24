from __future__ import annotations

import html
import random
import re
from typing import Any


CHARACTER_CONDITIONS = (
    ('unconscious', 'Без сознания'),
    ('poisoned', 'Отравлен'),
    ('stunned', 'Оглушён'),
    ('frightened', 'Испуган'),
    ('prone', 'Лежит'),
    ('concentration', 'Концентрация'),
)
CONDITION_LABELS = dict(CHARACTER_CONDITIONS)

_DICE_PATTERN = re.compile(r'^(\d*)d(\d+)([+-]\d+)?$')
_ADVANTAGE_PATTERN = re.compile(r'^(adv|dis)([+-]\d+)?$')


def condition_label(value: str) -> str:
    return CONDITION_LABELS.get(str(value or '').strip(), str(value or '').strip())


def format_conditions(conditions: list[str]) -> str:
    if not conditions:
        return 'нет'
    return ', '.join(html.escape(condition_label(value)) for value in conditions)


def format_condition_details(conditions: list[dict[str, Any]]) -> str:
    if not conditions:
        return 'нет'
    duration_labels = {'manual': '', 'rest': 'до отдыха', 'turns': 'ход.', 'rounds': 'раунд.'}
    result = []
    for row in conditions:
        kind = str(row.get('duration_kind') or 'manual')
        label = duration_labels.get(kind, '')
        if kind in {'turns', 'rounds'}:
            suffix = f' ({int(row.get("remaining") or 0)} {label})'
        elif label:
            suffix = f' ({label})'
        else:
            suffix = ''
        result.append(html.escape(condition_label(str(row.get('condition') or ''))) + suffix)
    return ', '.join(result)


def format_session_card(session: dict[str, Any]) -> str:
    def value(name: str, fallback: str = 'не указано') -> str:
        clean = str(session.get(name) or '').strip()
        return html.escape(clean) if clean else fallback

    return (
        f'🗓️ <b>{html.escape(str(session.get("title") or "Сессия"))}</b>\n\n'
        f'Следующая игра: <b>{value("next_session_text")}</b>\n\n'
        f'🎯 <b>Текущая цель</b>\n{value("current_goal")}\n\n'
        f'📖 <b>Где остановились</b>\n{value("last_recap")}\n\n'
        f'📌 <b>Важная заметка</b>\n{value("session_note")}'
    )


def format_initiative(encounter: dict[str, Any] | None) -> str:
    if not encounter:
        return '⚔️ <b>Инициатива</b>\n\nСейчас активного боя нет.'
    current = encounter.get('current')
    current_id = int(current['character_id']) if current else None
    lines = [
        f'⚔️ <b>Инициатива: {html.escape(str(encounter.get("session_title") or "Сессия"))}</b>',
        f'Раунд: <b>{int(encounter.get("round_number") or 1)}</b>',
    ]
    for entry in encounter.get('entries') or []:
        character_id = int(entry['character_id'])
        marker = '➡️' if current_id == character_id else '•'
        roll_value = 'не бросал' if entry.get('roll_value') is None else str(int(entry['roll_value']))
        lines.append(f'{marker} <b>{html.escape(str(entry["display_name"]))}</b>: {roll_value}')
    return '\n'.join(lines)


def roll_dice(expression: str, rng: Any = random) -> dict[str, Any]:
    clean = str(expression or '').strip().lower().replace(' ', '')
    if not clean:
        raise ValueError('Укажи бросок, например: /r d20+5')

    advantage_match = _ADVANTAGE_PATTERN.fullmatch(clean)
    if advantage_match:
        mode = advantage_match.group(1)
        modifier = int(advantage_match.group(2) or 0)
        if abs(modifier) > 1000:
            raise ValueError('Модификатор должен быть от -1000 до 1000.')
        rolls = [rng.randint(1, 20), rng.randint(1, 20)]
        chosen = max(rolls) if mode == 'adv' else min(rolls)
        return {
            'expression': clean,
            'mode': mode,
            'count': 2,
            'sides': 20,
            'rolls': rolls,
            'chosen': chosen,
            'modifier': modifier,
            'total': chosen + modifier,
        }

    dice_match = _DICE_PATTERN.fullmatch(clean)
    if not dice_match:
        raise ValueError('Формат броска: d20+5, 2d6+3, adv+4 или dis+2.')

    count = int(dice_match.group(1) or 1)
    sides = int(dice_match.group(2))
    modifier = int(dice_match.group(3) or 0)
    if not 1 <= count <= 100:
        raise ValueError('Можно бросить от 1 до 100 кубиков за раз.')
    if not 2 <= sides <= 1000:
        raise ValueError('У кубика должно быть от 2 до 1000 граней.')
    if abs(modifier) > 1000:
        raise ValueError('Модификатор должен быть от -1000 до 1000.')

    rolls = [rng.randint(1, sides) for _ in range(count)]
    return {
        'expression': clean,
        'mode': 'normal',
        'count': count,
        'sides': sides,
        'rolls': rolls,
        'chosen': None,
        'modifier': modifier,
        'total': sum(rolls) + modifier,
    }


def format_roll(result: dict[str, Any]) -> str:
    modifier = int(result['modifier'])
    modifier_text = f'{modifier:+d}' if modifier else ''
    mode = result['mode']
    rolls = ', '.join(str(value) for value in result['rolls'])
    if mode in {'adv', 'dis'}:
        title = 'Преимущество' if mode == 'adv' else 'Помеха'
        return (
            f'🎲 <b>{title}</b>\n'
            f'Броски d20: <code>{rolls}</code>\n'
            f'Выбран: <b>{result["chosen"]}</b>{modifier_text}\n'
            f'Итог: <b>{result["total"]}</b>'
        )
    return (
        f'🎲 <b>{result["expression"]}</b>\n'
        f'Кубики: <code>{rolls}</code>\n'
        f'Модификатор: <b>{modifier_text or "0"}</b>\n'
        f'Итог: <b>{result["total"]}</b>'
    )
