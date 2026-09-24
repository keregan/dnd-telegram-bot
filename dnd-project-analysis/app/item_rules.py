from __future__ import annotations


EQUIPMENT_SLOTS = [
    ('weapon', 'Оружие'),
    ('armor', 'Броня'),
    ('accessory', 'Аксессуар'),
    ('container', 'Сумка/рюкзак'),
    ('gear', 'Снаряжение'),
    ('tool', 'Инструмент'),
]

EQUIPMENT_SLOT_TITLES = {value: title for value, title in EQUIPMENT_SLOTS}

CONSUMABLE_CATEGORY_VALUES = {'food', 'drink', 'consumable'}

CONSUMABLE_KEYWORDS = (
    'еда',
    'мяс',
    'пирог',
    'лепеш',
    'лепёш',
    'суп',
    'чай',
    'кофе',
    'сбитен',
    'сбитень',
    'вода',
    'настой',
    'зель',
    'эликсир',
    'склянк',
    'флакон',
    'порош',
    'пыль',
    'масло',
    'свиток',
    'свеч',
    'ракета',
    'фляг',
)

NON_CONSUMABLE_KEYWORDS = (
    'кружка бесконечного',
    'ложка',
    'зеркал',
    'камень тихого',
    'камень "я',
    'камень “я',
)

EQUIPMENT_CATEGORY_SLOTS = {
    'weapon': 'weapon',
    'armor': 'armor',
    'accessory': 'accessory',
}

EQUIPMENT_KEYWORDS = (
    ('weapon', ('меч', 'топор', 'кинжал', 'арбалет', 'посох', 'клинок')),
    ('armor', ('доспех', 'броня', 'щит', 'шлем', 'наручи', 'панцир')),
    ('accessory', ('кольц', 'перстен', 'перстень', 'амулет', 'браслет', 'медальон')),
    ('container', ('сумка', 'рюкзак')),
    ('gear', ('плащ', 'пояс', 'кошел', 'носки', 'шляпа')),
    ('tool', ('набор алхим', 'набор картограф', 'набор лекар', 'молоток', 'крюк')),
)


def normalize_text(value: str | None) -> str:
    return str(value or '').lower().replace('ё', 'е')


def equipment_slot_label(slot: str | None) -> str:
    clean = str(slot or '').strip()
    if not clean:
        return 'нет'
    return EQUIPMENT_SLOT_TITLES.get(clean, clean)


def infer_is_consumable(name: str, description: str = '', category: str | None = None) -> bool:
    category_value = str(category or '').strip()
    text = normalize_text(f'{name} {description}')
    if any(keyword in text for keyword in NON_CONSUMABLE_KEYWORDS):
        return False
    return category_value in CONSUMABLE_CATEGORY_VALUES or any(keyword in text for keyword in CONSUMABLE_KEYWORDS)


def infer_equipment_slot(name: str, description: str = '', category: str | None = None) -> str:
    category_value = str(category or '').strip()
    if category_value in EQUIPMENT_CATEGORY_SLOTS:
        return EQUIPMENT_CATEGORY_SLOTS[category_value]

    text = normalize_text(f'{name} {description}')
    for slot, keywords in EQUIPMENT_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return slot
    return ''


def infer_carry_bonus_kg(name: str, description: str = '', category: str | None = None) -> float:
    text = normalize_text(f'{name} {description} {category or ""}')
    if 'большой рюкзак' in text:
        return 40.0
    if 'средний рюкзак' in text:
        return 20.0
    if 'рюкзак' in text:
        return 20.0
    if 'сумка' in text:
        return 10.0
    return 0.0


def infer_speed_penalty(name: str, description: str = '', category: str | None = None) -> int:
    text = normalize_text(f'{name} {description} {category or ""}')
    if 'большой рюкзак' in text:
        return 10
    return 0
