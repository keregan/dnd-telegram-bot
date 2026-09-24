from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SECTION_LABELS = {
    'ability': 'Способности и умения',
    'feat': 'Черты',
    'proficiency': 'Владения',
    'skill': 'Навыки',
    'cantrip': 'Заговоры',
    'prepared_spell': 'Подготовленные заклинания',
    'spellbook': 'Книга заклинаний',
}

SKILL_LABELS = {
    'acrobatics': 'Акробатика',
    'animal handling': 'Уход за животными',
    'arcana': 'Магия',
    'athletics': 'Атлетика',
    'deception': 'Обман',
    'history': 'История',
    'insight': 'Проницательность',
    'intimidation': 'Запугивание',
    'investigation': 'Расследование',
    'medicine': 'Медицина',
    'nature': 'Природа',
    'perception': 'Восприятие',
    'performance': 'Выступление',
    'persuasion': 'Убеждение',
    'religion': 'Религия',
    'sleight of hand': 'Ловкость рук',
    'stealth': 'Скрытность',
    'survival': 'Выживание',
}

STAT_LABELS = {
    'str': 'Сила',
    'dex': 'Ловкость',
    'con': 'Телосложение',
    'int': 'Интеллект',
    'wis': 'Мудрость',
    'cha': 'Харизма',
}

TRANSLIT = str.maketrans({
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
})


def _value(container: dict[str, Any], key: str, default: Any = '') -> Any:
    value = container.get(key, default)
    if isinstance(value, dict) and 'value' in value:
        return value.get('value', default)
    return value


def _node_text(node: Any) -> str:
    if not isinstance(node, dict):
        return ''
    if node.get('type') == 'text':
        return str(node.get('text') or '')
    parts = [_node_text(child) for child in node.get('content') or []]
    return '\n'.join(part for part in parts if part).strip()


def _spoilers(document: Any) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get('type') == 'spoiler':
            title = ''
            description = ''
            for child in node.get('content') or []:
                if child.get('type') == 'spoilerSummary':
                    title = _node_text(child)
                elif child.get('type') == 'spoilerContent':
                    description = _node_text(child)
            if title:
                result.append((title.strip(), description.strip()))
            return
        for child in node.get('content') or []:
            walk(child)

    walk(document)
    return result


def _document(data: dict[str, Any], block: str) -> Any:
    value = ((data.get('text') or {}).get(block) or {}).get('value') or {}
    return value.get('data') if isinstance(value, dict) else value


def _entry(section: str, name: str, description: str = '', source_id: str = '') -> dict[str, Any]:
    return {
        'section': section,
        'name': re.sub(r'\s+', ' ', str(name or '')).strip(),
        'description': re.sub(r'\n{3,}', '\n\n', str(description or '')).strip(),
        'source_id': str(source_id or '').strip(),
    }


def _deduplicate(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    positions: dict[tuple[str, str], int] = {}
    for entry in entries:
        if not entry['name']:
            continue
        key = (entry['section'], re.sub(r'\W+', '', entry['name'].casefold()))
        if key in positions:
            old = result[positions[key]]
            if len(entry['description']) > len(old['description']):
                result[positions[key]] = entry
            continue
        positions[key] = len(result)
        result.append(entry)
    for index, entry in enumerate(result):
        entry['sort_order'] = index
    return result


def _login_for(name: str) -> str:
    login = name.casefold().translate(TRANSLIT)
    login = re.sub(r'[^a-z0-9]+', '_', login).strip('_')
    return login or 'character'


def parse_lss_character(path: str | Path, spell_catalog: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    source_path = Path(path)
    outer = json.loads(source_path.read_text(encoding='utf-8-sig'))
    data_raw = outer.get('data') or '{}'
    data = json.loads(data_raw) if isinstance(data_raw, str) else data_raw
    info = data.get('info') or {}
    raw_name = str(_value(data, 'name') or source_path.stem).strip()

    match = re.match(r'^(.*?)\s*\(\s*(.*?)\s+(\d+)\s*\)\s*$', raw_name)
    if not match or not match.group(3):
        raise ValueError('Имя должно оканчиваться на «(Имя игрока N)», где N — номер сессии.')
    display_name = match.group(1).strip()
    player_name = match.group(2).strip()
    session_number = int(match.group(3))

    entries: list[dict[str, Any]] = []
    entries.extend(_entry('ability', name, description) for name, description in _spoilers(_document(data, 'traits')))
    entries.extend(_entry('feat', name, description) for name, description in _spoilers(_document(data, 'feats')))
    entries.extend(_entry('proficiency', name, description) for name, description in _spoilers(_document(data, 'prof')))

    for stat_key, save in (data.get('saves') or {}).items():
        if bool(save.get('isProf')):
            stat = STAT_LABELS.get(stat_key, stat_key.upper())
            entries.append(_entry('proficiency', f'Спасбросок: {stat}', 'Персонаж владеет этим спасброском.'))

    for key, skill in (data.get('skills') or {}).items():
        if int(skill.get('isProf') or 0) <= 0:
            continue
        stat = STAT_LABELS.get(str(skill.get('baseStat') or ''), str(skill.get('baseStat') or ''))
        entries.append(_entry('skill', SKILL_LABELS.get(key, key.title()), f'Владение навыком. Базовая характеристика: {stat}.'))

    resources = data.get('resources') or {}
    for resource_id, resource in resources.items():
        if str(resource_id).startswith('resource:spell-fixed:') or resource.get('isDeleted'):
            continue
        raw = str(resource.get('name') or '').strip()
        if not raw:
            continue
        split = re.split(r'[:.]\s+', raw, maxsplit=1)
        name = split[0]
        description = split[1] if len(split) > 1 else ''
        entries.append(_entry('ability', name, description, resource_id))
        if 'огненный снаряд' in raw.casefold():
            entries.append(_entry('cantrip', 'Огненный снаряд', raw, resource_id))

    catalog = spell_catalog or {}
    spell_config = outer.get('spells') or {}
    prepared_ids = {str(item) for item in spell_config.get('prepared') or []}
    granted_ids = {str(item.get('id')) for item in spell_config.get('granted') or [] if item.get('id')}
    cantrip_ids: set[str] = set()
    prepared_ids_from_wizard: set[str] = set()
    for choice_key, choice in ((outer.get('wizard') or {}).get('choices') or {}).items():
        ids = {str(item) for item in (choice or {}).get('spells') or []}
        if str(choice_key).endswith('#c0'):
            cantrip_ids.update(ids)
        elif str(choice_key).endswith('#c1'):
            prepared_ids_from_wizard.update(ids)
    known_names: dict[str, str] = {}
    for resource_id, resource in resources.items():
        prefix = 'resource:spell-fixed:'
        if str(resource_id).startswith(prefix):
            known_names[str(resource_id)[len(prefix):]] = str(resource.get('name') or '')

    all_ids = list(dict.fromkeys([
        *(str(item) for item in spell_config.get('book') or []),
        *prepared_ids,
        *granted_ids,
    ]))
    for spell_id in all_ids:
        spell = catalog.get(spell_id) or {}
        level = spell.get('level')
        name = str(spell.get('name') or known_names.get(spell_id) or f'Заклинание LSS {spell_id[-6:]}')
        description = str(spell.get('description') or '').strip()
        if not description:
            description = f'Описание отсутствует в экспорте Long Story Short. Исходный ID: {spell_id}.'
        if level == 0 or spell_id in cantrip_ids:
            section = 'cantrip'
        elif spell_id in prepared_ids or spell_id in prepared_ids_from_wizard or spell_id in granted_ids:
            section = 'prepared_spell'
        else:
            section = 'spellbook'
        entries.append(_entry(section, name, description, spell_id))

    return {
        'login': _login_for(display_name),
        'display_name': display_name,
        'player_name': player_name,
        'session_number': session_number,
        'session_title': f'Сессия {session_number}',
        'class_name': str(_value(info, 'charClass')).strip(),
        'subclass_name': str(_value(info, 'charSubclass')).strip(),
        'race_name': str(_value(info, 'race')).strip(),
        'background_name': str(_value(info, 'background')).strip(),
        'alignment': str(_value(info, 'alignment')).strip(),
        'level': max(1, int(_value(info, 'level', 1) or 1)),
        'xp': max(0, int(_value(info, 'experience', 0) or 0)),
        'gold': max(0, int(((data.get('coins') or {}).get('gp') or {}).get('value') or 0)),
        'strength_score': max(1, int(((data.get('stats') or {}).get('str') or {}).get('score') or 10)),
        'source_name': source_path.name,
        'entries': _deduplicate(entries),
    }
