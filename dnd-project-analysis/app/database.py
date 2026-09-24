from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
import random
import sqlite3

import aiosqlite

from app.assistant_features import AssistantFeaturesMixin
from app.gameplay import CONDITION_LABELS
from app.item_rules import infer_carry_bonus_kg, infer_equipment_slot, infer_is_consumable, infer_speed_penalty
from app.levels import enrich_character
from app.security import create_password_hash, verify_password


UNLIMITED_STOCK = -1
SQLITE_BUSY_TIMEOUT_MS = 5_000
LOGIN_MAX_FAILED_ATTEMPTS = 5
LOGIN_LOCK_MINUTES = 5
DATABASE_HARDENING_MIGRATION = '2026_09_18_database_hardening_v1'
GAMEPLAY_ASSISTANT_MIGRATION = '2026_09_18_gameplay_assistant_v1'
CATALOG_CORRECTIONS_MIGRATION = '2026_09_19_catalog_corrections_v1'

DEFAULT_ITEM_CATEGORIES = [
    ('weapon', '⚔️ Оружие'),
    ('armor', '🛡️ Броня'),
    ('food', '🍖 Еда'),
    ('drink', '🍺 Питьё'),
    ('magic', '✨ Магия'),
    ('tools', '🧰 Инструменты'),
    ('consumable', '🧪 Расходники'),
    ('gear', '🎒 Снаряжение'),
    ('accessory', '📿 Аксессуары'),
    ('other', '📦 Другое'),
]

AUTO_CATEGORIZE_MIGRATION = '2026_07_04_auto_item_categories_v1'

SUGGESTED_ITEMS_MIGRATION = '2026_07_04_suggested_shop_items_v3'
CHARACTER_ITEMS_MIGRATION = '2026_09_21_character_shop_items_v1'
REMOVED_ITEM_NAMES = {'набор писаря'}

DEFAULT_SESSION_TITLE = 'Общая сессия'
DEFAULT_SESSION_DESCRIPTION = 'Сессия по умолчанию для старых персонажей.'

ITEM_IMAGE_MIGRATION = '2026_07_04_local_item_images_v2'
ITEM_LOCAL_IMAGES = {
    'Копьё путешественника': 'assets/items/traveler_spear.png',
    'Короткий лук': 'assets/items/shortbow.png',
    'Посеребрённые болты ×5': 'assets/items/silvered_bolts.png',
    'Лом': 'assets/items/crowbar.png',
    'Набор маскировки': 'assets/items/disguise_kit.png',
    'Набор травника': 'assets/items/herbalism_kit.png',
    'Шарики в мешочке': 'assets/items/ball_bearings.png',
    'Калтропы': 'assets/items/caltrops.png',
    'Противоядие': 'assets/items/antitoxin.png',
    'Лечебная мазь': 'assets/items/healing_salve.png',
    'Зелье ночного зрения': 'assets/items/night_vision_potion.png',
    'Пыль истинного контура': 'assets/items/true_outline_dust.png',
    'Водонепроницаемый тубус': 'assets/items/waterproof_map_case.png',
    'Складной шест': 'assets/items/collapsible_pole.png',
    'Плащ непогоды': 'assets/items/weatherproof_cloak.png',
    'Монеты тихого разговора': 'assets/items/whisper_coins.png',
    'Мел возвращающегося пути': 'assets/items/returning_path_chalk.png',
    'Брошь сосредоточения': 'assets/items/focus_brooch.png',
    'Фонарь следов': 'assets/items/trail_lantern.png',
    'Колокольчик лжи': 'assets/items/bell_of_lies.png',
    'Перчатки осторожного вора': 'assets/items/careful_thief_gloves.png',
    'Метательный топор': 'assets/items/throwing_axe.png',
    'Короткий меч': 'assets/items/short_sword.png',
    'Посох странника': 'assets/items/wanderer_staff.png',
    'Серебряный кинжал': 'assets/items/silver_dagger.png',
    'Ржавый меч на удачу': 'assets/items/rusty_lucky_sword.png',
    'Клинок обратного удара': 'assets/items/rebound_blade.png',
    'Арбалет Громового Судьи': 'assets/items/thunder_judge_crossbow.png',
    'Топор голодной луны': 'assets/items/hungry_moon_axe.png',
    'Стёганый доспех': 'assets/items/quilted_armor.png',
    'Усиленные наручи': 'assets/items/reinforced_bracers.png',
    'Шлем дозорного': 'assets/items/watchman_helmet.png',
    'Плащ путешественника': 'assets/items/traveler_cloak.png',
    'Щит с трещиной': 'assets/items/cracked_shield.png',
    'Панцирь упрямого краба': 'assets/items/stubborn_crab_carapace.png',
    'Плащ последнего укрытия': 'assets/items/last_shelter_cloak.png',
    'Доспех треснувшей звезды': 'assets/items/cracked_star_armor.png',
    'Сырные лепёшки': 'assets/items/cheese_flatbreads.png',
    'Солёное мясо': 'assets/items/salted_meat.png',
    'Суп в дорожной фляге': 'assets/items/travel_flask_soup.png',
    'Яблочный пирог': 'assets/items/apple_pie.png',
    'Сухофрукты и орехи': 'assets/items/dried_fruits_nuts.png',
    'Травяной настой': 'assets/items/herbal_infusion.png',
    'Горячий сбитень': 'assets/items/hot_sbiten.png',
    'Вода из святого источника': 'assets/items/holy_spring_water.png',
    'Гномий крепкий кофе': 'assets/items/dwarven_strong_coffee.png',
    'Кружка бесконечного недовольства': 'assets/items/mug_endless_discontent.png',
    'Свиток тумана': 'assets/items/fog_scroll.png',
    'Камень тихого шага': 'assets/items/silent_step_stone.png',
    'Пыль светляков': 'assets/items/firefly_dust.png',
    'Малый кристалл маны': 'assets/items/small_mana_crystal.png',
    'Зеркальце правды': 'assets/items/mirror_of_truth.png',
    'Ложка, которая знает дорогу к супу': 'assets/items/soupfinder_spoon.png',
    'Камень “я это запомнил”': 'assets/items/memory_stone.png',
    'Кристалл маны с трещиной': 'assets/items/cracked_mana_crystal.png',
    'Лунный чай': 'assets/items/moon_tea.png',
    'Набор алхимика': 'assets/items/alchemist_kit.png',
    'Набор картографа': 'assets/items/cartographer_kit.png',
    'Набор лекаря': 'assets/items/healer_kit.png',
    'Молоток и клинья': 'assets/items/hammer_and_wedges.png',
    'Кислотная склянка': 'assets/items/acid_vial.png',
    'Масло для оружия': 'assets/items/weapon_oil.png',
    'Мешочек стеклянной пыли': 'assets/items/glass_dust_pouch.png',
    'Сигнальная ракета': 'assets/items/signal_flare.png',
    'Порошок сна': 'assets/items/sleep_powder.png',
    'Свеча последнего аргумента': 'assets/items/last_argument_candle.png',
    'Фляга с двойным дном': 'assets/items/double_bottom_flask.png',
    'Маленькое зеркало': 'assets/items/small_mirror.png',
    'Набор крюков': 'assets/items/hook_set.png',
    'Маскировочный плащ': 'assets/items/camouflage_cloak.png',
    'Пояс с карманами': 'assets/items/pocket_belt.png',
    'Верёвка с характером': 'assets/items/personality_rope.png',
    'Амулет спокойного сна': 'assets/items/calm_sleep_amulet.png',
    'Кольцо мелкой удачи': 'assets/items/minor_luck_ring.png',
    'Браслет следопыта': 'assets/items/tracker_bracelet.png',
    'Медальон старого героя': 'assets/items/old_hero_medallion.png',
    'Перстень торговца': 'assets/items/merchant_ring.png',
    'Носки бесшумного позора': 'assets/items/socks_of_silent_shame.png',
    'Монета “почти удачи”': 'assets/items/coin_almost_luck.png',
    'Шляпа подозрительно важного человека': 'assets/items/suspiciously_important_hat.png',
    'Плащ драматичного выхода': 'assets/items/dramatic_exit_cloak.png',
    'Глазастый кошелёк': 'assets/items/eyed_wallet.png',
    'Сумка': 'assets/items/satchel_bag.png',
    'Рюкзак': 'assets/items/medium_backpack.png',
    'Средний рюкзак': 'assets/items/medium_backpack.png',
    'Большой рюкзак': 'assets/items/large_backpack.png',
    'Компас неизбранной дороги': 'assets/items/wayward_compass.png',
    'Сапоги одолженного шага': 'assets/items/borrowed_step_boots.png',
    'Фонарь второй тени': 'assets/items/second_shadow_lantern.png',
    'Песочные часы малого возврата': 'assets/items/small_reversal_hourglass.png',
    'Фляга громкой тишины': 'assets/items/loud_silence_flask.png',
    'Нить общей удачи': 'assets/items/shared_fortune_thread.png',
    'Мел подслушивающей двери': 'assets/items/listening_door_chalk.png',
    'Монета честного долга': 'assets/items/honest_debt_coin.png',
    'Ножны запомненной стали': 'assets/items/remembered_steel_scabbard.png',
    'Осколок отложенной раны': 'assets/items/deferred_wound_mirror.png',
    'Свиток Щита': 'assets/items/shield_scroll.png',
    'Чернильница быстрого переписывания': 'assets/items/quick_scribing_inkwell.png',
    'Жезл направленного воплощения': 'assets/items/directed_evocation_wand.png',
    'Нить дальней мысли': 'assets/items/far_thought_thread.png',
    'Флакон внутреннего резонанса': 'assets/items/inner_resonance_vial.png',
    'Рубин боевого мага': 'assets/items/war_mage_ruby.png',
    'Двуручный меч строевого мага +1': 'assets/items/war_mage_greatsword_plus_one.png',
    'Печать драконьего дыхания': 'assets/items/dragon_breath_seal.png',
}

ITEM_WEIGHT_MIGRATION = '2026_07_05_item_weights_v1'
ITEM_USAGE_MIGRATION = '2026_07_05_item_usage_equipment_v1'
ITEM_SELL_PRICE_MIGRATION = '2026_07_06_item_sell_prices_v1'
ITEM_CARRY_CONTAINER_MIGRATION = '2026_07_06_carry_containers_v1'
ITEM_CATEGORY_CORRECTIONS = {
    'Арбалет': 'weapon',
    'Лук "Грамдаля"': 'weapon',
    'Кирка': 'tools',
    'Набор целителя': 'tools',
}
HEALING_ITEM_VALUES = {
    'Зелье лечение малое': 8,
    'Зелье лечение среднее': 18,
    'Зелье лечение большое': 36,
    'Лечебная мазь': 6,
}
# Приблизительные веса в килограммах. Часть значений основана на базовых весах DnD 5e,
# часть — на здравой оценке для пользовательских предметов магазина.
ITEM_WEIGHTS_KG = {
    'Метательный топор': 0.9,
    'Короткий меч': 0.9,
    'Посох странника': 2.0,
    'Серебряный кинжал': 0.45,
    'Ржавый меч на удачу': 1.4,
    'Клинок обратного удара': 1.6,
    'Арбалет Громового Судьи': 8.2,
    'Топор голодной луны': 3.2,
    'Стёганый доспех': 4.0,
    'Усиленные наручи': 1.2,
    'Шлем дозорного': 1.5,
    'Плащ путешественника': 1.2,
    'Щит с трещиной': 2.7,
    'Панцирь упрямого краба': 9.0,
    'Плащ последнего укрытия': 1.5,
    'Доспех треснувшей звезды': 7.5,
    'Сырные лепёшки': 0.4,
    'Солёное мясо': 0.5,
    'Суп в дорожной фляге': 1.0,
    'Яблочный пирог': 0.8,
    'Сухофрукты и орехи': 0.3,
    'Травяной настой': 0.5,
    'Горячий сбитень': 0.5,
    'Вода из святого источника': 0.5,
    'Гномий крепкий кофе': 0.6,
    'Кружка бесконечного недовольства': 0.7,
    'Свиток тумана': 0.1,
    'Камень тихого шага': 0.2,
    'Пыль светляков': 0.1,
    'Малый кристалл маны': 0.3,
    'Зеркальце правды': 0.4,
    'Ложка, которая знает дорогу к супу': 0.05,
    'Камень “я это запомнил”': 0.25,
    'Кристалл маны с трещиной': 0.5,
    'Лунный чай': 0.4,
    'Набор алхимика': 4.0,
    'Набор картографа': 2.0,
    'Набор лекаря': 2.5,
    'Молоток и клинья': 3.0,
    'Кислотная склянка': 0.5,
    'Масло для оружия': 0.3,
    'Мешочек стеклянной пыли': 0.2,
    'Сигнальная ракета': 0.4,
    'Порошок сна': 0.15,
    'Свеча последнего аргумента': 0.3,
    'Фляга с двойным дном': 0.6,
    'Маленькое зеркало': 0.2,
    'Набор крюков': 1.5,
    'Маскировочный плащ': 1.3,
    'Пояс с карманами': 0.8,
    'Верёвка с характером': 5.0,
    'Амулет спокойного сна': 0.05,
    'Кольцо мелкой удачи': 0.02,
    'Браслет следопыта': 0.1,
    'Медальон старого героя': 0.15,
    'Перстень торговца': 0.05,
    'Носки бесшумного позора': 0.15,
    'Монета “почти удачи”': 0.02,
    'Шляпа подозрительно важного человека': 0.5,
    'Плащ драматичного выхода': 1.5,
    'Глазастый кошелёк': 0.3,
    'Сумка': 1.0,
    'Средний рюкзак': 2.0,
    'Большой рюкзак': 3.0,
}

DEFAULT_STRENGTH_SCORE = 10
KG_PER_STRENGTH_POINT = 6.8  # 15 lb из DnD 5e ≈ 6.8 кг


def carry_capacity_from_strength(strength_score: int | float | None) -> float:
    try:
        strength = max(1, int(strength_score or DEFAULT_STRENGTH_SCORE))
    except (TypeError, ValueError):
        strength = DEFAULT_STRENGTH_SCORE
    return round(strength * KG_PER_STRENGTH_POINT, 1)


def default_sell_price(price: int | float | None) -> int:
    try:
        clean_price = max(0, int(price or 0))
    except (TypeError, ValueError):
        clean_price = 0
    return int(clean_price * 0.8)

SUGGESTED_SHOP_ITEMS = [{'category': 'weapon',
  'name': 'Метательный топор',
  'price': 25,
  'rarity': 'common',
  'shop_quantity': 12,
  'description': 'Урон: 1d6 рубящий. Можно бросить на 6/18 м. Простое оружие для ближнего боя и короткой дистанции.'},
 {'category': 'weapon',
  'name': 'Короткий меч',
  'price': 80,
  'rarity': 'common',
  'shop_quantity': 10,
  'description': 'Урон: 1d6 колющий. Лёгкое фехтовальное оружие для быстрых атак и боя в тесных местах.'},
 {'category': 'weapon',
  'name': 'Посох странника',
  'price': 40,
  'rarity': 'common',
  'shop_quantity': 10,
  'description': 'Урон: 1d6 дробящий, двумя руками 1d8. Помогает в дороге и подходит как простое оружие.'},
 {'category': 'weapon',
  'name': 'Серебряный кинжал',
  'price': 150,
  'rarity': 'uncommon',
  'shop_quantity': 6,
  'description': 'Урон: 1d4 колющий. Считается серебряным оружием против существ с уязвимостью к серебру.'},
 {'category': 'weapon',
  'name': 'Ржавый меч на удачу',
  'price': 20,
  'rarity': 'common',
  'shop_quantity': 15,
  'description': 'Урон: 1d6 рубящий. При натуральной 20 добавь +1d4 урона. При натуральной 1 меч трескается или даёт -1 к следующей атаке.'},
 {'category': 'weapon',
  'name': 'Клинок обратного удара',
  'price': 950,
  'rarity': 'epic',
  'shop_quantity': 2,
  'description': 'Оружие для игроков 8 уровня. Урон: 2d8 рубящий + 1d6 силовой. При критическом ударе цель теряет реакцию до начала своего хода. Минус: при '
                 'натуральной 1 владелец получает 1d6 силового урона.'},
 {'category': 'weapon',
  'name': 'Арбалет Громового Судьи',
  'price': 1100,
  'rarity': 'epic',
  'shop_quantity': 2,
  'description': 'Оружие для игроков 8 уровня. Урон: 2d10 колющий + 1d8 громовой. При попадании цель отталкивается на 3 м, если провалит Силу СЛ 14. Минус: '
                 'после выстрела владельца слышно издалека, Скрытность невозможна до конца следующего хода.'},
 {'category': 'weapon',
  'name': 'Топор голодной луны',
  'price': 1250,
  'rarity': 'legendary',
  'shop_quantity': 1,
  'description': 'Оружие для игроков 8 уровня. Урон: 2d12 рубящий. Если цель ниже половины HP, добавь +1d8 некротического урона. Минус: если за бой не нанёс '
                 'урон этим топором, после боя получаешь -1 к следующей проверке Мудрости.'},
 {'category': 'armor',
  'name': 'Стёганый доспех',
  'price': 50,
  'rarity': 'common',
  'shop_quantity': 15,
  'description': 'КД: 11 + модификатор Ловкости. Лёгкая броня из плотной ткани. Минус: даёт помеху к Скрытности, если промокла или сильно шуршит.'},
 {'category': 'armor',
  'name': 'Усиленные наручи',
  'price': 70,
  'rarity': 'common',
  'shop_quantity': 10,
  'description': 'Один раз за бой можно уменьшить урон от атаки оружием на 1d4. Не считается полноценной бронёй.'},
 {'category': 'armor',
  'name': 'Шлем дозорного',
  'price': 90,
  'rarity': 'common',
  'shop_quantity': 10,
  'description': '+1 к проверкам Внимательности против засады и летящих предметов. Минус: в шлеме хуже слышно шёпот.'},
 {'category': 'armor',
  'name': 'Плащ путешественника',
  'price': 60,
  'rarity': 'common',
  'shop_quantity': 15,
  'description': '+1 к Выживанию в дождь, холод или сильный ветер. Помогает скрыть мелкие предметы под одеждой.'},
 {'category': 'armor',
  'name': 'Щит с трещиной',
  'price': 35,
  'rarity': 'common',
  'shop_quantity': 12,
  'description': '+1 к КД вместо обычного щита. Один раз можно принять удар на щит и сломать его, уменьшив урон на 1d8.'},
 {'category': 'armor',
  'name': 'Панцирь упрямого краба',
  'price': 800,
  'rarity': 'rare',
  'shop_quantity': 3,
  'description': '+1 к КД. Владельца нельзя сдвинуть против его воли, если он стоит на земле. Минус: скорость снижается на 1,5 м.'},
 {'category': 'armor',
  'name': 'Плащ последнего укрытия',
  'price': 650,
  'rarity': 'rare',
  'shop_quantity': 3,
  'description': 'Если HP ниже 25%, владелец получает преимущество на Скрытность на 10 минут. Минус: при ярком свете эффект не работает.'},
 {'category': 'armor',
  'name': 'Доспех треснувшей звезды',
  'price': 1200,
  'rarity': 'epic',
  'shop_quantity': 2,
  'description': '+1 к КД. Один раз за бой можно уменьшить входящий урон на 2d6. Минус: после использования владелец светится до конца боя и получает -2 к '
                 'Скрытности.'},
 {'category': 'food',
  'name': 'Сырные лепёшки',
  'price': 8,
  'rarity': 'common',
  'shop_quantity': 20,
  'description': 'После короткого отдыха даёт 1 временный HP. Простая плотная еда для дороги.'},
 {'category': 'food',
  'name': 'Солёное мясо',
  'price': 15,
  'rarity': 'common',
  'shop_quantity': 20,
  'description': 'Порция на 1 день пути. Даёт +1 к проверке Телосложения против голода или усталости от марша.'},
 {'category': 'food',
  'name': 'Суп в дорожной фляге',
  'price': 12,
  'rarity': 'common',
  'shop_quantity': 15,
  'description': 'Если выпить во время короткого отдыха, можно восстановить 1d4 HP. Через сутки прокисает.'},
 {'category': 'food',
  'name': 'Яблочный пирог',
  'price': 18,
  'rarity': 'common',
  'shop_quantity': 10,
  'description': 'На 1 сцену даёт +1 к проверке Харизмы в мирном разговоре, если поделиться с NPC.'},
 {'category': 'food',
  'name': 'Сухофрукты и орехи',
  'price': 10,
  'rarity': 'common',
  'shop_quantity': 20,
  'description': 'Быстрый перекус. На 1 час снимает штрафы от лёгкого голода и помогает держать темп в дороге.'},
 {'category': 'drink',
  'name': 'Травяной настой',
  'price': 12,
  'rarity': 'common',
  'shop_quantity': 15,
  'description': 'На 1 час даёт +1 к спасброску Телосложения против яда, болезни или холода.'},
 {'category': 'drink',
  'name': 'Горячий сбитень',
  'price': 10,
  'rarity': 'common',
  'shop_quantity': 15,
  'description': 'На 2 часа даёт +1 к проверкам против холода и плохой погоды.'},
 {'category': 'drink',
  'name': 'Вода из святого источника',
  'price': 50,
  'rarity': 'uncommon',
  'shop_quantity': 8,
  'description': 'Можно выпить, чтобы получить +1 к спасброску против нежити на 1 час, или бросить во врага-нежить на 2d6 лучистого урона.'},
 {'category': 'drink',
  'name': 'Гномий крепкий кофе',
  'price': 25,
  'rarity': 'uncommon',
  'shop_quantity': 8,
  'description': 'На 4 часа даёт преимущество против сна и магической сонливости. Минус: после эффекта -1 к Внимательности на 1 час.'},
 {'category': 'drink',
  'name': 'Кружка бесконечного недовольства',
  'price': 80,
  'rarity': 'uncommon',
  'shop_quantity': 5,
  'description': 'Любой напиток становится горьким. В таверне даёт +1 к Запугиванию дворфов и ворчунов на 1 сцену.'},
 {'category': 'magic',
  'name': 'Свиток тумана',
  'price': 350,
  'rarity': 'uncommon',
  'shop_quantity': 6,
  'description': 'Одноразовый. Создаёт туман радиусом 6 м на 10 минут. Сильный ветер рассеивает туман за 1 минуту. Минус: владелец тоже не видит сквозь '
                 'туман.'},
 {'category': 'magic',
  'name': 'Камень тихого шага',
  'price': 300,
  'rarity': 'uncommon',
  'shop_quantity': 5,
  'description': '+2 к Скрытности на 10 минут. Минус: после эффекта владелец 10 минут может говорить только шёпотом.'},
 {'category': 'magic',
  'name': 'Пыль светляков',
  'price': 120,
  'rarity': 'common',
  'shop_quantity': 10,
  'description': 'Одноразовая. Освещает 6 м ярким светом и ещё 12 м тусклым на 1 час. На 10 минут подсвечивает свежие следы. Минус: свет может привлечь '
                 'существ поблизости.'},
 {'category': 'magic',
  'name': 'Малый кристалл маны',
  'price': 150,
  'rarity': 'uncommon',
  'shop_quantity': 5,
  'description': 'Одноразовый. Восстанавливает 1 ячейку заклинания 1 уровня. Если ячеек нет, даёт +1d4 к следующей проверке Магии.'},
 {'category': 'magic',
  'name': 'Зеркальце правды',
  'price': 450,
  'rarity': 'rare',
  'shop_quantity': 3,
  'description': '1 раз в день в течение 1 минуты помогает проверить иллюзию, маскировку или ложный облик. Минус: при провале показывает неприятную, но '
                 'бесполезную правду о владельце.'},
 {'category': 'magic',
  'name': 'Ложка, которая знает дорогу к супу',
  'price': 120,
  'rarity': 'uncommon',
  'shop_quantity': 5,
  'description': '1 раз в день на 10 минут указывает на ближайшую съедобную горячую еду в пределах 1 км. Минус: не отличает суп от ловушки с супом.'},
 {'category': 'magic',
  'name': 'Камень “я это запомнил”',
  'price': 160,
  'rarity': 'uncommon',
  'shop_quantity': 5,
  'description': 'Нагревается, когда рядом кто-то повторяет уже совершённую ошибку. 1 раз в день даёт +1 к Проницательности на 1 сцену. Минус: иногда '
                 'реагирует на самого владельца.'},
 {'category': 'magic',
  'name': 'Кристалл маны с трещиной',
  'price': 500,
  'rarity': 'rare',
  'shop_quantity': 3,
  'description': 'Одноразовый. Восстанавливает 1 ячейку заклинания 1 уровня или добавляет +1d6 к урону заклинания. Минус: после использования брось d20, на '
                 '1–4 получаешь 1d6 силового урона.'},
 {'category': 'magic',
  'name': 'Лунный чай',
  'price': 250,
  'rarity': 'uncommon',
  'shop_quantity': 6,
  'description': 'После питья на 1 час даёт вдохновение или +1 к следующей проверке Мудрости. Минус: после отдыха брось d20, на 1–3 просыпаешься тревожным и '
                 'получаешь -1 к первой проверке дня.'},
 {'category': 'tools',
  'name': 'Набор алхимика',
  'price': 200,
  'rarity': 'uncommon',
  'shop_quantity': 5,
  'description': '+2 к проверкам создания простого зелья, кислоты или анализа жидкости. Работа обычно занимает 10 минут или больше.'},
 {'category': 'tools',
  'name': 'Набор картографа',
  'price': 120,
  'rarity': 'common',
  'shop_quantity': 8,
  'description': '+2 к проверкам карт, маршрутов и ориентирования на 1 сцену путешествия.'},
 {'category': 'tools',
  'name': 'Набор лекаря',
  'price': 100,
  'rarity': 'common',
  'shop_quantity': 10,
  'description': '3 использования. Можно стабилизировать существо или за 10 минут перевязки восстановить 1d6 HP один раз за короткий отдых.'},
 {'category': 'tools',
  'name': 'Молоток и клинья',
  'price': 50,
  'rarity': 'common',
  'shop_quantity': 12,
  'description': '+2 к проверкам закрепления двери, установки верёвки или работы в пещере. В наборе 10 клиньев.'},
 {'category': 'consumable',
  'name': 'Кислотная склянка',
  'price': 80,
  'rarity': 'common',
  'shop_quantity': 10,
  'description': 'Одноразовая. Бросок на 6 м. При попадании наносит 2d6 кислотного урона.'},
 {'category': 'consumable',
  'name': 'Масло для оружия',
  'price': 30,
  'rarity': 'common',
  'shop_quantity': 15,
  'description': 'Действует 10 минут. Следующие 3 попадания оружием получают +1 к урону. Одно использование.'},
 {'category': 'consumable',
  'name': 'Мешочек стеклянной пыли',
  'price': 45,
  'rarity': 'common',
  'shop_quantity': 12,
  'description': 'Одноразовый. Покрывает область 3 м на 10 минут, проявляет следы и может выдать невидимое существо по отпечаткам.'},
 {'category': 'consumable',
  'name': 'Сигнальная ракета',
  'price': 60,
  'rarity': 'common',
  'shop_quantity': 10,
  'description': 'Одноразовая. Светит 1 минуту, видна примерно за 1 км в открытой местности.'},
 {'category': 'consumable',
  'name': 'Порошок сна',
  'price': 100,
  'rarity': 'uncommon',
  'shop_quantity': 6,
  'description': 'Одноразовый. Облако 3 м. Существа с низкой стойкостью делают спасбросок Телосложения СЛ 13 или засыпают/становятся сонными на 1 минуту.'},
 {'category': 'consumable',
  'name': 'Свеча последнего аргумента',
  'price': 280,
  'rarity': 'uncommon',
  'shop_quantity': 5,
  'description': 'Горит 10 минут. Даёт +2 к Убеждению или Запугиванию на один разговор. Минус: после разговора цель может понять, что на неё давили магией.'},
 {'category': 'gear',
  'name': 'Фляга с двойным дном',
  'price': 75,
  'rarity': 'common',
  'shop_quantity': 10,
  'description': 'Позволяет спрятать монеты, записку или мелкий предмет. Найти тайник можно проверкой Расследования СЛ 15.'},
 {'category': 'gear',
  'name': 'Маленькое зеркало',
  'price': 20,
  'rarity': 'common',
  'shop_quantity': 15,
  'description': '+1 к проверке ловушек или засады, если есть время аккуратно посмотреть за угол.'},
 {'category': 'gear',
  'name': 'Набор крюков',
  'price': 60,
  'rarity': 'common',
  'shop_quantity': 10,
  'description': '+2 к проверке Атлетики для подъёма, закрепления верёвки или пересечения стены на 1 сцену.'},
 {'category': 'gear',
  'name': 'Маскировочный плащ',
  'price': 160,
  'rarity': 'uncommon',
  'shop_quantity': 6,
  'description': 'После 1 минуты подготовки даёт +1 к Скрытности на природе или в руинах на 1 час.'},
 {'category': 'gear',
  'name': 'Пояс с карманами',
  'price': 45,
  'rarity': 'common',
  'shop_quantity': 12,
  'description': 'Вмещает 5 мелких предметов. 1 раз за ход можно достать один мелкий предмет без лишней возни.'},
 {'category': 'gear',
  'name': 'Верёвка с характером',
  'price': 90,
  'rarity': 'uncommon',
  'shop_quantity': 5,
  'description': 'Длина 15 м. +2 к проверкам узлов и связывания. Минус: при натуральной 1 завязывает неправильный узел.'},
 {'category': 'accessory',
  'name': 'Амулет спокойного сна',
  'price': 180,
  'rarity': 'uncommon',
  'shop_quantity': 5,
  'description': 'Во время отдыха даёт преимущество к спасброскам против кошмаров, страха и слабых проклятий сна.'},
 {'category': 'accessory',
  'name': 'Кольцо мелкой удачи',
  'price': 250,
  'rarity': 'uncommon',
  'shop_quantity': 4,
  'description': '1 раз в день можно перебросить d20, но второй результат обязателен. Минус: после использования -1 к следующей проверке.'},
 {'category': 'accessory',
  'name': 'Браслет следопыта',
  'price': 160,
  'rarity': 'uncommon',
  'shop_quantity': 5,
  'description': '+2 к Выживанию для поиска следов на 1 час. Минус: при натуральной 1 ведёт по ложному следу.'},
 {'category': 'accessory',
  'name': 'Медальон старого героя',
  'price': 300,
  'rarity': 'rare',
  'shop_quantity': 3,
  'description': '+1 к Убеждению с ветеранами, стражей или простыми жителями, если показать медальон. Может быть сюжетным ключом.'},
 {'category': 'accessory',
  'name': 'Перстень торговца',
  'price': 220,
  'rarity': 'uncommon',
  'shop_quantity': 4,
  'description': '1 раз в день даёт +2 к Торговле/Убеждению при покупке или продаже. Минус: при провале продавец может поднять цену.'},
 {'category': 'accessory',
  'name': 'Носки бесшумного позора',
  'price': 90,
  'rarity': 'uncommon',
  'shop_quantity': 6,
  'description': '+2 к Скрытности на 10 минут. Минус: при провале Скрытности носки громко хлюпают и выдают владельца.'},
 {'category': 'accessory',
  'name': 'Монета “почти удачи”',
  'price': 400,
  'rarity': 'rare',
  'shop_quantity': 2,
  'description': 'Одноразовая. Игрок может перебросить d20. Минус: мастер получает право один раз заставить этого игрока перебросить успешный бросок.'},
 {'category': 'accessory',
  'name': 'Шляпа подозрительно важного человека',
  'price': 200,
  'rarity': 'uncommon',
  'shop_quantity': 4,
  'description': 'На 10 минут даёт +2 к Обману или Убеждению, чтобы выглядеть официально. Минус: если обман раскрыт, дальше проверки идут с помехой.'},
 {'category': 'accessory',
  'name': 'Плащ драматичного выхода',
  'price': 220,
  'rarity': 'uncommon',
  'shop_quantity': 5,
  'description': '+2 к Выступлению или Запугиванию на 1 сцену эффектного ухода. Минус: при провале персонаж выглядит максимально глупо.'},
 {'category': 'accessory',
  'name': 'Глазастый кошелёк',
  'price': 180,
  'rarity': 'uncommon',
  'shop_quantity': 5,
  'description': 'Пищит при попытке кражи, если вор не прошёл Ловкость рук СЛ 15. Минус: иногда пищит без причины в неудобный момент.'},
 {'category': 'gear',
  'name': 'Сумка',
  'price': 35,
  'rarity': 'common',
  'shop_quantity': 12,
  'description': 'Если экипирована, даёт +10 кг к переносимому весу.'},
 {'category': 'gear',
  'name': 'Средний рюкзак',
  'price': 75,
  'rarity': 'common',
  'shop_quantity': 10,
  'description': 'Если экипирован, даёт +20 кг к переносимому весу.'},
 {'category': 'gear',
  'name': 'Большой рюкзак',
  'price': 150,
  'rarity': 'uncommon',
  'shop_quantity': 6,
  'description': 'Если экипирован, даёт +40 кг к переносимому весу, но скорость снижается на 10.'}]

SUGGESTED_SHOP_ITEMS += [
    {
        'category': 'weapon',
        'name': 'Копьё путешественника',
        'price': 30,
        'rarity': 'common',
        'shop_quantity': 10,
        'weight_kg': 1.4,
        'equipment_slot': 'weapon',
        'description': 'Урон: 1d6 колющий, двумя руками 1d8. Можно метнуть на 6/18 м. Простое надёжное копьё для дороги, охоты и проверки опасных проходов.',
    },
    {
        'category': 'weapon',
        'name': 'Короткий лук',
        'price': 70,
        'rarity': 'common',
        'shop_quantity': 8,
        'weight_kg': 0.9,
        'equipment_slot': 'weapon',
        'description': 'Урон: 1d6 колющий. Дистанция 24/96 м. Компактный лук для охоты и боя в лесу.',
    },
    {
        'category': 'consumable',
        'name': 'Посеребрённые болты ×5',
        'price': 60,
        'rarity': 'uncommon',
        'shop_quantity': 8,
        'weight_kg': 0.4,
        'is_consumable': True,
        'description': 'Набор из пяти арбалетных болтов с серебряным покрытием. Считается серебряным боеприпасом против существ, чувствительных к серебру. Расходуется как один набор по решению мастера.',
    },
    {
        'category': 'tools',
        'name': 'Лом',
        'price': 15,
        'rarity': 'common',
        'shop_quantity': 12,
        'weight_kg': 2.3,
        'equipment_slot': 'tool',
        'description': 'Даёт +2 к проверке Силы, когда его можно использовать как рычаг: открыть ящик, дверь, решётку или сдвинуть тяжёлый предмет.',
    },
    {
        'category': 'tools',
        'name': 'Набор маскировки',
        'price': 80,
        'rarity': 'common',
        'shop_quantity': 6,
        'weight_kg': 1.4,
        'equipment_slot': 'tool',
        'description': 'Грим, красители, накладные волосы и мелкие детали одежды. Позволяет подготовить правдоподобное изменение внешности при наличии времени.',
    },
    {
        'category': 'tools',
        'name': 'Набор травника',
        'price': 90,
        'rarity': 'common',
        'shop_quantity': 6,
        'weight_kg': 1.4,
        'equipment_slot': 'tool',
        'description': 'Ножницы, ступка, мешочки и простые реактивы. Нужен для распознавания растений и приготовления обычных настоев, мазей и противоядий.',
    },
    {
        'category': 'consumable',
        'name': 'Шарики в мешочке',
        'price': 10,
        'rarity': 'common',
        'shop_quantity': 15,
        'weight_kg': 0.9,
        'is_consumable': True,
        'description': 'Одноразовый мешочек. Рассыпается на участке до 3 м. Существо, быстро проходящее через участок, делает проверку Ловкости СЛ 10 или падает.',
    },
    {
        'category': 'consumable',
        'name': 'Калтропы',
        'price': 15,
        'rarity': 'common',
        'shop_quantity': 12,
        'weight_kg': 0.9,
        'is_consumable': True,
        'description': 'Одноразовый мешочек металлических шипов на участок 1,5 м. Неосторожное существо делает проверку Ловкости СЛ 15; при провале получает 1 урон и теряет часть скорости до лечения.',
    },
    {
        'category': 'consumable',
        'name': 'Противоядие',
        'price': 60,
        'rarity': 'common',
        'shop_quantity': 8,
        'weight_kg': 0.1,
        'is_consumable': True,
        'description': 'Одноразовый флакон. Снимает состояние «Отравлен» от обычного яда либо даёт преимущество к следующему спасброску против сильного яда — по решению мастера.',
    },
    {
        'category': 'consumable',
        'name': 'Лечебная мазь',
        'price': 45,
        'rarity': 'common',
        'shop_quantity': 10,
        'weight_kg': 0.2,
        'is_consumable': True,
        'heal_hp': 6,
        'description': 'Одноразовая баночка густой лечебной мази. При использовании бот автоматически восстанавливает 6 HP, но не выше максимума.',
    },
    {
        'category': 'consumable',
        'name': 'Зелье ночного зрения',
        'price': 140,
        'rarity': 'uncommon',
        'shop_quantity': 5,
        'weight_kg': 0.2,
        'is_consumable': True,
        'description': 'Одноразовое. На 1 час позволяет видеть в темноте на 18 м в оттенках серого. Яркий свет после употребления кажется неприятным.',
    },
    {
        'category': 'consumable',
        'name': 'Пыль истинного контура',
        'price': 160,
        'rarity': 'uncommon',
        'shop_quantity': 5,
        'weight_kg': 0.1,
        'is_consumable': True,
        'description': 'Одноразовый пакет. Облако радиусом 3 м на 1 минуту обрисовывает невидимых существ и скрытые границы предметов мерцающим контуром.',
    },
    {
        'category': 'gear',
        'name': 'Водонепроницаемый тубус',
        'price': 25,
        'rarity': 'common',
        'shop_quantity': 10,
        'weight_kg': 0.5,
        'equipment_slot': 'gear',
        'description': 'Плотный кожаный тубус с восковой пропиткой. Защищает карты, письма и один небольшой свиток от дождя и краткого погружения.',
    },
    {
        'category': 'gear',
        'name': 'Складной шест',
        'price': 18,
        'rarity': 'common',
        'shop_quantity': 8,
        'weight_kg': 0.7,
        'equipment_slot': 'gear',
        'description': 'Секции раскрываются в шест длиной 3 м. Подходит для проверки пола и ловушек, измерения глубины и подтягивания лёгких предметов.',
    },
    {
        'category': 'armor',
        'name': 'Плащ непогоды',
        'price': 110,
        'rarity': 'uncommon',
        'shop_quantity': 6,
        'weight_kg': 1.2,
        'equipment_slot': 'armor',
        'description': 'Плотный пропитанный плащ. Даёт преимущество к проверкам против обычного дождя, ветра и холода, но не защищает от магической погоды.',
    },
    {
        'category': 'magic',
        'name': 'Монеты тихого разговора',
        'price': 180,
        'rarity': 'uncommon',
        'shop_quantity': 4,
        'weight_kg': 0.1,
        'description': 'Парные монеты. Раз в долгий отдых владелец одной монеты может передать владельцу второй сообщение до 12 слов, если обе монеты находятся в одном мире.',
    },
    {
        'category': 'consumable',
        'name': 'Мел возвращающегося пути',
        'price': 70,
        'rarity': 'uncommon',
        'shop_quantity': 10,
        'weight_kg': 0.1,
        'is_consumable': True,
        'description': 'Одноразовый кусок мела. Оставленные им метки в течение 24 часов видны только тому, кто их нарисовал, и существам, которым он указал на метку.',
    },
    {
        'category': 'accessory',
        'name': 'Брошь сосредоточения',
        'price': 280,
        'rarity': 'uncommon',
        'shop_quantity': 4,
        'weight_kg': 0.1,
        'equipment_slot': 'accessory',
        'description': 'Пока брошь надета, владелец получает +1 к проверкам поддержания концентрации. Бонус не складывается с другой такой брошью.',
    },
    {
        'category': 'magic',
        'name': 'Фонарь следов',
        'price': 240,
        'rarity': 'uncommon',
        'shop_quantity': 4,
        'weight_kg': 1.0,
        'equipment_slot': 'gear',
        'description': 'Раз в долгий отдых можно зажечь на 10 минут. В его свете свежие следы не старше суток мерцают слабым янтарным светом.',
    },
    {
        'category': 'magic',
        'name': 'Колокольчик лжи',
        'price': 320,
        'rarity': 'rare',
        'shop_quantity': 3,
        'weight_kg': 0.2,
        'description': 'Раз в долгий отдых тихо звенит, когда выбранное существо рядом произносит заведомую ложь. Не определяет недоговорённость и ошибочное убеждение.',
    },
    {
        'category': 'accessory',
        'name': 'Перчатки осторожного вора',
        'price': 260,
        'rarity': 'uncommon',
        'shop_quantity': 4,
        'weight_kg': 0.3,
        'equipment_slot': 'accessory',
        'description': 'Раз за сессию позволяют перебросить неудачную проверку инструментами вора. Второй результат обязателен. Не помогают, если ловушка уже сработала.',
    },
]

CHARACTER_SHOP_ITEMS = [
    {'category': 'consumable', 'name': 'Свиток Щита', 'price': 140, 'rarity': 'uncommon', 'shop_quantity': 2, 'weight_kg': 0.1, 'is_consumable': True, 'equipment_slot': '', 'description': 'Одноразовый свиток с заклинанием «Щит». Когда владельца поражает атака или он становится целью «Волшебной стрелы», свиток можно прочитать реакцией: до начала следующего хода владелец получает +5 к КД, в том числе против вызвавшей реакцию атаки, и не получает урон от «Волшебной стрелы». После применения пергамент рассыпается серебряной пылью.'},
    {'category': 'tools', 'name': 'Чернильница быстрого переписывания', 'price': 180, 'rarity': 'uncommon', 'shop_quantity': 2, 'weight_kg': 0.3, 'is_consumable': True, 'equipment_slot': '', 'description': 'Одноразовый запас зачарованных чернил для волшебника. При переносе одного заклинания 1-го или 2-го уровня в книгу заклинаний вдвое уменьшает необходимое время и стоимость материалов. Чернил хватает ровно на одно заклинание; эффект не складывается с другой такой чернильницей.'},
    {'category': 'magic', 'name': 'Жезл направленного воплощения', 'price': 420, 'rarity': 'uncommon', 'shop_quantity': 2, 'weight_kg': 0.7, 'is_consumable': False, 'equipment_slot': 'weapon', 'description': 'Магическая фокусировка для заклинателя. Пока жезл находится в руке, владелец получает +1 к броскам атаки заклинаниями. Заклинания школы Воплощения, сотворённые через жезл, игнорируют половинное укрытие цели. Жезл не повышает сложность спасброска заклинаний.'},
    {'category': 'accessory', 'name': 'Нить дальней мысли', 'price': 260, 'rarity': 'uncommon', 'shop_quantity': 2, 'weight_kg': 0.05, 'is_consumable': False, 'equipment_slot': 'accessory', 'description': 'Парные браслеты, соединённые невидимой нитью. Раз в долгий отдых два согласных существа могут надеть их и установить телепатическую связь на 10 минут. Пока они находятся на одном плане и не дальше 120 футов друг от друга, каждый может мысленно передавать другому короткие фразы; общий язык не требуется, но передаются только слова и простые образы.'},
    {'category': 'magic', 'name': 'Флакон внутреннего резонанса', 'price': 460, 'rarity': 'uncommon', 'shop_quantity': 2, 'weight_kg': 0.2, 'is_consumable': False, 'equipment_slot': 'accessory', 'description': 'Многоразовый чародейский фокус. Раз в долгий отдых после завершения короткого отдыха владелец может настроиться на колебания флакона и восстановить 2 потраченных Очка чародейства, но не выше своего обычного максимума. Если внутри нет отклика, флакон остаётся тусклым до следующего долгого отдыха.'},
    {'category': 'accessory', 'name': 'Рубин боевого мага', 'price': 260, 'rarity': 'uncommon', 'shop_quantity': 2, 'weight_kg': 0.1, 'is_consumable': False, 'equipment_slot': 'accessory', 'description': 'За короткий отдых рубин можно закрепить на одном простом или воинском оружии. Пока камень закреплён, это оружие можно использовать как магическую фокусировку для заклинаний владельца. Перенос рубина на другое оружие требует нового короткого отдыха; сам камень не делает оружие магическим и не даёт бонуса к атаке или урону.'},
    {'category': 'weapon', 'name': 'Двуручный меч строевого мага +1', 'price': 520, 'rarity': 'uncommon', 'shop_quantity': 2, 'weight_kg': 2.7, 'is_consumable': False, 'equipment_slot': 'weapon', 'description': 'Добротный двуручный меч, рассчитанный на бой в доспехах и работу рядом с заклинаниями. Даёт +1 к броскам атаки и урона этим оружием и считается магическим для преодоления сопротивления и иммунитета к немагическим атакам. Требует владения двуручным мечом и двух свободных рук для атаки.'},
    {'category': 'accessory', 'name': 'Печать драконьего дыхания', 'price': 340, 'rarity': 'uncommon', 'shop_quantity': 2, 'weight_kg': 0.1, 'is_consumable': False, 'equipment_slot': 'accessory', 'description': 'Талисман для драконорождённого, откликающийся на наследственную стихию. Раз в долгий отдых сразу после броска урона оружия дыхания владелец может перебросить все кости урона и выбрать один из двух общих результатов. Тип урона, область, сложность спасброска и число применений дыхания печать не изменяет.'},
    {'category': 'gear', 'name': 'Ножны запомненной стали', 'price': 700, 'rarity': 'rare', 'shop_quantity': 2, 'weight_kg': 0.8, 'is_consumable': False, 'equipment_slot': 'gear', 'description': 'Ножны подходят для одного меча или кинжала. Раз в короткий отдых, когда владелец получает урон кислотой, холодом, огнём, молнией или звуком, ножны могут запомнить этот тип урона. Следующее попадание вложенным оружием в течение 1 минуты наносит дополнительно 1d6 запомненного типа, после чего энергия исчезает.'},
]

SUGGESTED_SHOP_ITEMS += [
    {
        'category': 'accessory',
        'name': 'Компас неизбранной дороги',
        'price': 520,
        'rarity': 'rare',
        'shop_quantity': 3,
        'loot_chance_percent': 3,
        'weight_kg': 0.4,
        'equipment_slot': 'accessory',
        'description': 'Для персонажей 5–7 уровня. Раз в долгий отдых после 1 минуты изучения местности указывает направление к ближайшему известному безопасному проходу в пределах 1 км. Не показывает путь к цели; если безопасных дорог несколько, выбирает одну случайно.',
    },
    {
        'category': 'armor',
        'name': 'Сапоги одолженного шага',
        'price': 650,
        'rarity': 'rare',
        'shop_quantity': 3,
        'loot_chance_percent': 3,
        'is_active': False,
        'weight_kg': 1.1,
        'equipment_slot': 'armor',
        'description': 'Для персонажей 5–7 уровня. Раз в короткий отдых реакцией можно переместиться в свободное место, которое союзник в пределах 9 м покинул в этом раунде. После перемещения скорость владельца равна 0 до начала его следующего хода.',
    },
    {
        'category': 'magic',
        'name': 'Фонарь второй тени',
        'price': 480,
        'rarity': 'uncommon',
        'shop_quantity': 4,
        'loot_chance_percent': 5,
        'is_active': False,
        'weight_kg': 1.0,
        'equipment_slot': 'gear',
        'description': 'Для персонажей 5–7 уровня. Раз в долгий отдых создаёт рядом с владельцем ложную тень до начала его следующего хода: первая атака по владельцу совершается с помехой. При включении фонарь гасит все обычные источники огня в радиусе 3 м.',
    },
    {
        'category': 'magic',
        'name': 'Песочные часы малого возврата',
        'price': 850,
        'rarity': 'rare',
        'shop_quantity': 2,
        'loot_chance_percent': 2,
        'weight_kg': 0.6,
        'description': 'Для персонажей 5–7 уровня. Раз в долгий отдых сразу после своего хода владелец может вернуться в свободное место, где начал этот ход. Урон, лечение, потраченные действия, заряды и предметы не возвращаются.',
    },
    {
        'category': 'consumable',
        'name': 'Фляга громкой тишины',
        'price': 220,
        'rarity': 'uncommon',
        'shop_quantity': 6,
        'loot_chance_percent': 7,
        'is_active': False,
        'weight_kg': 0.2,
        'is_consumable': True,
        'description': 'Для персонажей 5–7 уровня. Одноразовая. На 1 минуту создаёт сферу радиусом 3 м: звук из неё не выходит наружу, но внутри даже шёпот звучит оглушительно. Снаружи разговор и заклинания не слышны; внутри проверки слуха совершаются с помехой.',
    },
    {
        'category': 'accessory',
        'name': 'Нить общей удачи',
        'price': 750,
        'rarity': 'rare',
        'shop_quantity': 2,
        'loot_chance_percent': 2,
        'weight_kg': 0.2,
        'equipment_slot': 'accessory',
        'description': 'Для персонажей 5–7 уровня. Парные браслеты. Раз в долгий отдых, когда два связанных союзника в пределах 18 м бросили d20, они могут поменяться результатами до объявления исхода. После обмена оба не могут использовать реакции до начала своего следующего хода.',
    },
    {
        'category': 'consumable',
        'name': 'Мел подслушивающей двери',
        'price': 180,
        'rarity': 'uncommon',
        'shop_quantity': 7,
        'loot_chance_percent': 8,
        'weight_kg': 0.1,
        'is_consumable': True,
        'description': 'Для персонажей 5–7 уровня. Одноразовый. Нарисованный на немагической стене контур на 10 минут становится односторонним окном для зрения и слуха. Через него нельзя пройти, атаковать или передавать предметы.',
    },
    {
        'category': 'accessory',
        'name': 'Монета честного долга',
        'price': 620,
        'rarity': 'rare',
        'shop_quantity': 3,
        'loot_chance_percent': 3,
        'weight_kg': 0.05,
        'equipment_slot': 'accessory',
        'description': 'Для персонажей 5–7 уровня. Раз в долгий отдых после броска d20 можно добавить 1d6. До следующего отдыха мастер вычитает 1d6 из другого броска владельца. Пока долг не выплачен, монета не восстанавливает заряд.',
    },
    {
        'category': 'gear',
        'name': 'Ножны запомненной стали',
        'price': 700,
        'rarity': 'rare',
        'shop_quantity': 3,
        'loot_chance_percent': 3,
        'is_active': False,
        'weight_kg': 0.8,
        'equipment_slot': 'gear',
        'description': 'Для персонажей 5–7 уровня. Раз в короткий отдых после получения урона кислотой, холодом, огнём, молнией или громом ножны запоминают его тип. Следующее попадание вложенным оружием наносит дополнительно 1d6 этого типа; энергия исчезает через 1 минуту.',
    },
    {
        'category': 'accessory',
        'name': 'Осколок отложенной раны',
        'price': 780,
        'rarity': 'rare',
        'shop_quantity': 2,
        'loot_chance_percent': 2,
        'weight_kg': 0.3,
        'equipment_slot': 'accessory',
        'description': 'Для персонажей 5–7 уровня. Раз в долгий отдых реакцией откладывает до 10 полученного урона до конца следующего хода владельца. Отложенный урон нельзя уменьшить; если владелец раньше падает до 0 HP, он получает его немедленно.',
    },
]



def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Database(AssistantFeaturesMixin):
    def __init__(self, path: str):
        self.path = path

    @asynccontextmanager
    async def connect(self):
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute('PRAGMA foreign_keys = ON')
        await db.execute(f'PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}')
        try:
            yield db
        finally:
            await db.close()

    async def _ensure_column(self, db: aiosqlite.Connection, table: str, column: str, ddl: str) -> None:
        cursor = await db.execute(f'PRAGMA table_info({table})')
        columns = {row['name'] for row in await cursor.fetchall()}
        if column not in columns:
            await db.execute(f'ALTER TABLE {table} ADD COLUMN {ddl}')

    async def _add_journal_entry(
        self,
        db: aiosqlite.Connection,
        character_id: int,
        event_type: str,
        title: str,
        details: str = '',
        actor_telegram_id: int | None = None,
    ) -> None:
        await db.execute(
            """
            INSERT INTO character_journal(character_id, actor_telegram_id, event_type, title, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(character_id),
                actor_telegram_id,
                str(event_type or 'note').strip() or 'note',
                str(title or 'Запись').strip() or 'Запись',
                str(details or '').strip(),
                now_iso(),
            ),
        )

    async def init(self) -> None:
        async with self.connect() as db:
            await db.execute('PRAGMA journal_mode = WAL')
            await db.execute('PRAGMA synchronous = NORMAL')
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS characters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE,
                    login TEXT NOT NULL UNIQUE,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0,
                    gold INTEGER NOT NULL DEFAULT 0,
                    hp INTEGER NOT NULL DEFAULT 10,
                    max_hp INTEGER NOT NULL DEFAULT 10,
                    session_id INTEGER,
                    strength_score INTEGER NOT NULL DEFAULT 10,
                    max_carry_kg REAL,
                    admin_notes TEXT NOT NULL DEFAULT '',
                    inspiration INTEGER NOT NULL DEFAULT 0,
                    initiative_bonus INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT
                );

                CREATE TABLE IF NOT EXISTS game_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    next_session_text TEXT NOT NULL DEFAULT '',
                    current_goal TEXT NOT NULL DEFAULT '',
                    last_recap TEXT NOT NULL DEFAULT '',
                    session_note TEXT NOT NULL DEFAULT '',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS shop_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    price INTEGER NOT NULL DEFAULT 0,
                    sell_price INTEGER NOT NULL DEFAULT 0,
                    rarity TEXT NOT NULL DEFAULT 'common',
                    category TEXT NOT NULL DEFAULT 'other',
                    image_file_id TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    shop_quantity INTEGER NOT NULL DEFAULT -1,
                    loot_chance_percent INTEGER NOT NULL DEFAULT 0,
                    weight_kg REAL NOT NULL DEFAULT 0,
                    is_consumable INTEGER NOT NULL DEFAULT 0,
                    equipment_slot TEXT NOT NULL DEFAULT '',
                    carry_bonus_kg REAL NOT NULL DEFAULT 0,
                    speed_penalty INTEGER NOT NULL DEFAULT 0,
                    heal_hp INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS item_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    value TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL UNIQUE,
                    sort_order INTEGER NOT NULL DEFAULT 100,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS inventory (
                    character_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (character_id, item_id),
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE,
                    FOREIGN KEY (item_id) REFERENCES shop_items(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS character_equipment (
                    character_id INTEGER NOT NULL,
                    slot TEXT NOT NULL,
                    item_id INTEGER NOT NULL,
                    equipped_at TEXT NOT NULL,
                    PRIMARY KEY (character_id, slot),
                    UNIQUE (character_id, item_id),
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE,
                    FOREIGN KEY (item_id) REFERENCES shop_items(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS quests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    xp_reward INTEGER NOT NULL DEFAULT 0,
                    gold_reward INTEGER NOT NULL DEFAULT 0,
                    item_id INTEGER,
                    item_quantity INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (item_id) REFERENCES shop_items(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS app_migrations (
                    name TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    character_id INTEGER,
                    admin_telegram_id INTEGER,
                    type TEXT NOT NULL,
                    amount INTEGER,
                    item_id INTEGER,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE SET NULL,
                    FOREIGN KEY (item_id) REFERENCES shop_items(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS character_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    character_id INTEGER NOT NULL,
                    actor_telegram_id INTEGER,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS character_sheets (
                    character_id INTEGER PRIMARY KEY,
                    player_name TEXT NOT NULL DEFAULT '',
                    class_name TEXT NOT NULL DEFAULT '',
                    subclass_name TEXT NOT NULL DEFAULT '',
                    race_name TEXT NOT NULL DEFAULT '',
                    background_name TEXT NOT NULL DEFAULT '',
                    alignment TEXT NOT NULL DEFAULT '',
                    level INTEGER NOT NULL DEFAULT 1,
                    source_name TEXT NOT NULL DEFAULT '',
                    imported_at TEXT NOT NULL,
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS character_sheet_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    character_id INTEGER NOT NULL,
                    section TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    source_id TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE,
                    UNIQUE (character_id, section, name)
                );

                CREATE TABLE IF NOT EXISTS quest_awards (
                    quest_id INTEGER NOT NULL,
                    character_id INTEGER NOT NULL,
                    admin_telegram_id INTEGER,
                    awarded_at TEXT NOT NULL,
                    PRIMARY KEY (quest_id, character_id),
                    FOREIGN KEY (quest_id) REFERENCES quests(id) ON DELETE CASCADE,
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS auth_attempts (
                    telegram_id INTEGER PRIMARY KEY,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    first_failed_at TEXT NOT NULL,
                    locked_until TEXT
                );

                CREATE TABLE IF NOT EXISTS character_conditions (
                    character_id INTEGER NOT NULL,
                    condition TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY (character_id, condition),
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS initiative_encounters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    round_number INTEGER NOT NULL DEFAULT 1,
                    turn_index INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    ended_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES game_sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS initiative_entries (
                    encounter_id INTEGER NOT NULL,
                    character_id INTEGER NOT NULL,
                    roll_value INTEGER,
                    rolled_at TEXT,
                    PRIMARY KEY (encounter_id, character_id),
                    FOREIGN KEY (encounter_id) REFERENCES initiative_encounters(id) ON DELETE CASCADE,
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
                );
                """
            )
            await self._ensure_column(db, 'characters', 'session_id', 'session_id INTEGER')
            await self._ensure_column(db, 'characters', 'strength_score', 'strength_score INTEGER NOT NULL DEFAULT 10')
            await self._ensure_column(db, 'characters', 'max_carry_kg', 'max_carry_kg REAL')
            await self._ensure_column(db, 'characters', 'hp', 'hp INTEGER NOT NULL DEFAULT 10')
            await self._ensure_column(db, 'characters', 'max_hp', 'max_hp INTEGER NOT NULL DEFAULT 10')
            await self._ensure_column(db, 'characters', 'admin_notes', "admin_notes TEXT NOT NULL DEFAULT ''")
            await self._ensure_column(db, 'characters', 'inspiration', 'inspiration INTEGER NOT NULL DEFAULT 0')
            await self._ensure_column(db, 'characters', 'initiative_bonus', 'initiative_bonus INTEGER NOT NULL DEFAULT 0')
            await self._ensure_column(db, 'game_sessions', 'next_session_text', "next_session_text TEXT NOT NULL DEFAULT ''")
            await self._ensure_column(db, 'game_sessions', 'current_goal', "current_goal TEXT NOT NULL DEFAULT ''")
            await self._ensure_column(db, 'game_sessions', 'last_recap', "last_recap TEXT NOT NULL DEFAULT ''")
            await self._ensure_column(db, 'game_sessions', 'session_note', "session_note TEXT NOT NULL DEFAULT ''")
            await self._ensure_column(db, 'shop_items', 'shop_quantity', 'shop_quantity INTEGER NOT NULL DEFAULT -1')
            await self._ensure_column(db, 'shop_items', 'loot_chance_percent', 'loot_chance_percent INTEGER NOT NULL DEFAULT 0')
            await self._ensure_column(db, 'shop_items', 'category', "category TEXT NOT NULL DEFAULT 'other'")
            await self._ensure_column(db, 'shop_items', 'sell_price', 'sell_price INTEGER NOT NULL DEFAULT 0')
            await self._ensure_column(db, 'shop_items', 'weight_kg', 'weight_kg REAL NOT NULL DEFAULT 0')
            await self._ensure_column(db, 'shop_items', 'is_consumable', 'is_consumable INTEGER NOT NULL DEFAULT 0')
            await self._ensure_column(db, 'shop_items', 'equipment_slot', "equipment_slot TEXT NOT NULL DEFAULT ''")
            await self._ensure_column(db, 'shop_items', 'carry_bonus_kg', 'carry_bonus_kg REAL NOT NULL DEFAULT 0')
            await self._ensure_column(db, 'shop_items', 'speed_penalty', 'speed_penalty INTEGER NOT NULL DEFAULT 0')
            await self._ensure_column(db, 'shop_items', 'heal_hp', 'heal_hp INTEGER NOT NULL DEFAULT 0')
            await self._init_assistant_features(db)
            await self._ensure_default_session(db)
            await self._seed_item_categories(db)
            await self._seed_suggested_shop_items(db)
            await self._seed_item_weights(db)
            await self._auto_categorize_existing_items(db, force=False)
            await self._seed_item_usage_flags(db)
            await self._seed_item_sell_prices(db)
            await self._seed_carry_container_stats(db)
            await self._seed_character_shop_items(db)
            await self._assign_local_item_images(db)
            await self._apply_database_hardening(db)
            await self._apply_gameplay_assistant_migration(db)
            await db.commit()

    async def health_summary(self) -> dict[str, Any]:
        async with self.connect() as db:
            integrity = (await (await db.execute('PRAGMA quick_check')).fetchone())[0]
            foreign_key_issues = len(await (await db.execute('PRAGMA foreign_key_check')).fetchall())
            characters = (await (await db.execute('SELECT COUNT(*) FROM characters')).fetchone())[0]
            items = (await (await db.execute('SELECT COUNT(*) FROM shop_items')).fetchone())[0]
            sessions = (await (await db.execute('SELECT COUNT(*) FROM game_sessions')).fetchone())[0]
        return {
            'integrity': str(integrity),
            'foreign_key_issues': int(foreign_key_issues),
            'characters': int(characters),
            'items': int(items),
            'sessions': int(sessions),
        }

    async def _apply_database_hardening(self, db: aiosqlite.Connection) -> None:
        await db.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS characters_values_nonnegative_insert
            BEFORE INSERT ON characters
            WHEN NEW.xp < 0 OR NEW.gold < 0 OR NEW.hp < 0 OR NEW.max_hp < 1
            BEGIN
                SELECT RAISE(ABORT, 'character values must be nonnegative');
            END;

            CREATE TRIGGER IF NOT EXISTS characters_values_nonnegative_update
            BEFORE UPDATE OF xp, gold, hp, max_hp ON characters
            WHEN NEW.xp < 0 OR NEW.gold < 0 OR NEW.hp < 0 OR NEW.max_hp < 1
            BEGIN
                SELECT RAISE(ABORT, 'character values must be nonnegative');
            END;

            CREATE TRIGGER IF NOT EXISTS shop_stock_valid_insert
            BEFORE INSERT ON shop_items
            WHEN NEW.shop_quantity < -1
            BEGIN
                SELECT RAISE(ABORT, 'shop stock must be -1 or greater');
            END;

            CREATE TRIGGER IF NOT EXISTS shop_stock_valid_update
            BEFORE UPDATE OF shop_quantity ON shop_items
            WHEN NEW.shop_quantity < -1
            BEGIN
                SELECT RAISE(ABORT, 'shop stock must be -1 or greater');
            END;
            """
        )
        await db.execute(
            'INSERT OR IGNORE INTO app_migrations(name, applied_at) VALUES (?, ?)',
            (DATABASE_HARDENING_MIGRATION, now_iso()),
        )

    async def _apply_gameplay_assistant_migration(self, db: aiosqlite.Connection) -> None:
        await db.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_character_conditions_character
            ON character_conditions(character_id);

            CREATE INDEX IF NOT EXISTS idx_initiative_encounters_session_active
            ON initiative_encounters(session_id, is_active);

            CREATE TRIGGER IF NOT EXISTS character_inspiration_valid_insert
            BEFORE INSERT ON characters
            WHEN NEW.inspiration NOT IN (0, 1)
            BEGIN
                SELECT RAISE(ABORT, 'inspiration must be 0 or 1');
            END;

            CREATE TRIGGER IF NOT EXISTS character_inspiration_valid_update
            BEFORE UPDATE OF inspiration ON characters
            WHEN NEW.inspiration NOT IN (0, 1)
            BEGIN
                SELECT RAISE(ABORT, 'inspiration must be 0 or 1');
            END;

            CREATE TRIGGER IF NOT EXISTS item_healing_nonnegative_insert
            BEFORE INSERT ON shop_items
            WHEN NEW.heal_hp < 0
            BEGIN
                SELECT RAISE(ABORT, 'item healing must be nonnegative');
            END;

            CREATE TRIGGER IF NOT EXISTS item_healing_nonnegative_update
            BEFORE UPDATE OF heal_hp ON shop_items
            WHEN NEW.heal_hp < 0
            BEGIN
                SELECT RAISE(ABORT, 'item healing must be nonnegative');
            END;
            """
        )
        await db.execute(
            'INSERT OR IGNORE INTO app_migrations(name, applied_at) VALUES (?, ?)',
            (GAMEPLAY_ASSISTANT_MIGRATION, now_iso()),
        )


    async def _ensure_default_session(self, db: aiosqlite.Connection) -> int:
        await db.execute(
            """
            INSERT OR IGNORE INTO game_sessions(title, description, is_active, created_at)
            VALUES (?, ?, 1, ?)
            """,
            (DEFAULT_SESSION_TITLE, DEFAULT_SESSION_DESCRIPTION, now_iso()),
        )
        cursor = await db.execute('SELECT id FROM game_sessions WHERE title = ?', (DEFAULT_SESSION_TITLE,))
        row = await cursor.fetchone()
        session_id = int(row['id'])
        await db.execute('UPDATE characters SET session_id = ? WHERE session_id IS NULL', (session_id,))
        return session_id

    async def list_sessions(self, only_active: bool = False) -> list[dict[str, Any]]:
        query = """
            SELECT gs.*, COUNT(c.id) AS characters_count
            FROM game_sessions gs
            LEFT JOIN characters c ON c.session_id = gs.id
        """
        params: list[Any] = []
        if only_active:
            query += ' WHERE gs.is_active = 1'
        query += ' GROUP BY gs.id ORDER BY gs.id ASC, gs.title COLLATE NOCASE ASC'
        async with self.connect() as db:
            cursor = await db.execute(query, tuple(params))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_session(self, session_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT gs.*, COUNT(c.id) AS characters_count
                FROM game_sessions gs
                LEFT JOIN characters c ON c.session_id = gs.id
                WHERE gs.id = ?
                GROUP BY gs.id
                """,
                (session_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_session(self, title: str, description: str = '') -> int:
        clean_title = title.strip()
        if len(clean_title) < 2:
            raise ValueError('Название сессии должно быть минимум 2 символа.')
        async with self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO game_sessions(title, description, is_active, created_at)
                VALUES (?, ?, 1, ?)
                """,
                (clean_title, description.strip(), now_iso()),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def update_session_card_field(self, session_id: int, field: str, value: str) -> tuple[bool, str]:
        labels = {
            'next_session_text': 'дата следующей игры',
            'current_goal': 'текущая цель',
            'last_recap': 'где остановились',
            'session_note': 'важная заметка',
        }
        if field not in labels:
            return False, 'Неизвестное поле карточки сессии.'
        clean_value = str(value or '').strip()
        if len(clean_value) > 600:
            return False, 'Текст слишком длинный. Максимум 600 символов.'
        async with self.connect() as db:
            cursor = await db.execute(
                f'UPDATE game_sessions SET {field} = ? WHERE id = ?',
                (clean_value, session_id),
            )
            if int(cursor.rowcount or 0) <= 0:
                return False, 'Сессия не найдена.'
            await db.commit()
        value_text = clean_value or 'очищено'
        return True, f'{labels[field].capitalize()}: {value_text}'

    async def start_initiative(self, session_id: int) -> tuple[bool, str, int | None]:
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            session_cursor = await db.execute('SELECT title FROM game_sessions WHERE id = ?', (session_id,))
            session = await session_cursor.fetchone()
            if session is None:
                return False, 'Сессия не найдена.', None
            characters_cursor = await db.execute(
                'SELECT id FROM characters WHERE session_id = ? ORDER BY display_name COLLATE NOCASE',
                (session_id,),
            )
            character_ids = [int(row['id']) for row in await characters_cursor.fetchall()]
            if not character_ids:
                return False, 'В этой сессии нет персонажей.', None
            now = now_iso()
            await db.execute(
                'UPDATE initiative_encounters SET is_active = 0, ended_at = ? WHERE session_id = ? AND is_active = 1',
                (now, session_id),
            )
            cursor = await db.execute(
                """
                INSERT INTO initiative_encounters(session_id, is_active, round_number, turn_index, created_at)
                VALUES (?, 1, 1, 0, ?)
                """,
                (session_id, now),
            )
            encounter_id = int(cursor.lastrowid)
            await db.executemany(
                'INSERT INTO initiative_entries(encounter_id, character_id) VALUES (?, ?)',
                [(encounter_id, character_id) for character_id in character_ids],
            )
            await db.commit()
            return True, f'Инициатива запущена для сессии «{session["title"]}».', encounter_id

    async def get_active_initiative(self, session_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            encounter_cursor = await db.execute(
                """
                SELECT ie.*, gs.title AS session_title
                FROM initiative_encounters ie
                JOIN game_sessions gs ON gs.id = ie.session_id
                WHERE ie.session_id = ? AND ie.is_active = 1
                ORDER BY ie.id DESC
                LIMIT 1
                """,
                (session_id,),
            )
            encounter = await encounter_cursor.fetchone()
            if encounter is None:
                return None
            entries_cursor = await db.execute(
                """
                SELECT ent.character_id, ent.roll_value, ent.rolled_at,
                       c.display_name, COALESCE(c.initiative_bonus, 0) AS initiative_bonus
                FROM initiative_entries ent
                JOIN characters c ON c.id = ent.character_id
                WHERE ent.encounter_id = ?
                ORDER BY CASE WHEN ent.roll_value IS NULL THEN 1 ELSE 0 END,
                         ent.roll_value DESC, c.display_name COLLATE NOCASE ASC
                """,
                (int(encounter['id']),),
            )
            entries = [dict(row) for row in await entries_cursor.fetchall()]
        result = dict(encounter)
        result['entries'] = entries
        rolled = [entry for entry in entries if entry['roll_value'] is not None]
        if rolled:
            current_index = int(result['turn_index']) % len(rolled)
            result['current'] = rolled[current_index]
        else:
            result['current'] = None
        return result

    async def get_character_active_initiative(self, character_id: int) -> dict[str, Any] | None:
        character = await self.get_character(character_id)
        if not character or character.get('session_id') is None:
            return None
        return await self.get_active_initiative(int(character['session_id']))

    async def roll_character_initiative(self, character_id: int) -> tuple[bool, str]:
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            cursor = await db.execute(
                """
                SELECT ent.encounter_id, ent.roll_value, c.display_name,
                       COALESCE(c.initiative_bonus, 0) AS initiative_bonus
                FROM initiative_entries ent
                JOIN initiative_encounters ie ON ie.id = ent.encounter_id AND ie.is_active = 1
                JOIN characters c ON c.id = ent.character_id AND c.session_id = ie.session_id
                WHERE ent.character_id = ?
                ORDER BY ent.encounter_id DESC
                LIMIT 1
                """,
                (character_id,),
            )
            entry = await cursor.fetchone()
            if entry is None:
                return False, 'Для твоей сессии сейчас нет активной инициативы.'
            if entry['roll_value'] is not None:
                return False, f'Инициатива уже брошена: {int(entry["roll_value"])}.'
            die = random.randint(1, 20)
            bonus = int(entry['initiative_bonus'] or 0)
            total = die + bonus
            await db.execute(
                """
                UPDATE initiative_entries
                SET roll_value = ?, rolled_at = ?
                WHERE encounter_id = ? AND character_id = ? AND roll_value IS NULL
                """,
                (total, now_iso(), int(entry['encounter_id']), character_id),
            )
            await db.commit()
            return True, f'{entry["display_name"]}: d20 ({die}) {bonus:+d} = {total}'

    async def advance_initiative(self, encounter_id: int) -> tuple[bool, str]:
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            encounter_cursor = await db.execute(
                'SELECT * FROM initiative_encounters WHERE id = ? AND is_active = 1',
                (encounter_id,),
            )
            encounter = await encounter_cursor.fetchone()
            if encounter is None:
                return False, 'Активная инициатива не найдена.'
            count_cursor = await db.execute(
                'SELECT COUNT(*) AS count FROM initiative_entries WHERE encounter_id = ? AND roll_value IS NOT NULL',
                (encounter_id,),
            )
            rolled_count = int((await count_cursor.fetchone())['count'])
            if rolled_count <= 0:
                return False, 'Сначала хотя бы один персонаж должен бросить инициативу.'
            old_index = int(encounter['turn_index']) % rolled_count
            new_index = (old_index + 1) % rolled_count
            new_round = int(encounter['round_number']) + (1 if new_index == 0 else 0)
            await self._tick_temporary_conditions(db, 'turns')
            if new_round > int(encounter['round_number']):
                await self._tick_temporary_conditions(db, 'rounds')
            await db.execute(
                'UPDATE initiative_encounters SET turn_index = ?, round_number = ? WHERE id = ?',
                (new_index, new_round, encounter_id),
            )
            await db.commit()
            return True, f'Ход передан. Раунд {new_round}.'

    async def end_initiative(self, encounter_id: int) -> tuple[bool, str]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                UPDATE initiative_encounters
                SET is_active = 0, ended_at = ?
                WHERE id = ? AND is_active = 1
                """,
                (now_iso(), encounter_id),
            )
            if int(cursor.rowcount or 0) <= 0:
                return False, 'Активная инициатива не найдена.'
            await db.commit()
            return True, 'Инициатива завершена.'

    async def set_character_session(self, character_id: int, session_id: int) -> tuple[bool, str]:
        async with self.connect() as db:
            char_cursor = await db.execute('SELECT display_name FROM characters WHERE id = ?', (character_id,))
            character = await char_cursor.fetchone()
            if character is None:
                return False, 'Персонаж не найден.'
            session_cursor = await db.execute('SELECT title FROM game_sessions WHERE id = ?', (session_id,))
            session = await session_cursor.fetchone()
            if session is None:
                return False, 'Сессия не найдена.'
            await db.execute('UPDATE characters SET session_id = ? WHERE id = ?', (session_id, character_id))
            await self._add_journal_entry(
                db,
                character_id,
                'session_changed',
                'Сессия изменена',
                f'Персонаж перенесён в сессию: {session["title"]}.',
            )
            await db.commit()
            return True, f'Персонаж {character["display_name"]} перенесён в сессию: {session["title"]}.'

    async def _seed_item_categories(self, db: aiosqlite.Connection) -> None:
        """Create default categories and keep user-created categories safe.

        v6 stores categories in `item_categories`.  If the admin already created
        a category with the same visible title, for example `📿 Аксессуары`, we
        keep its current value (`cat_19` etc.) instead of creating a duplicate.
        """
        for sort_order, (value, title) in enumerate(DEFAULT_ITEM_CATEGORIES):
            cursor = await db.execute('SELECT id FROM item_categories WHERE value = ?', (value,))
            row = await cursor.fetchone()
            if row:
                await db.execute(
                    'UPDATE item_categories SET title = ?, sort_order = ? WHERE value = ?',
                    (title, sort_order, value),
                )
                continue

            title_cursor = await db.execute('SELECT id FROM item_categories WHERE title = ?', (title,))
            title_row = await title_cursor.fetchone()
            if title_row:
                await db.execute(
                    'UPDATE item_categories SET sort_order = ? WHERE id = ?',
                    (sort_order, int(title_row['id'])),
                )
                continue

            await db.execute(
                """
                INSERT INTO item_categories(value, title, sort_order, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (value, title, sort_order, now_iso()),
            )

        cursor = await db.execute("SELECT DISTINCT COALESCE(category, 'other') AS category FROM shop_items")
        rows = await cursor.fetchall()
        known_values = {value for value, _ in DEFAULT_ITEM_CATEGORIES}
        for row in rows:
            value = (row['category'] or 'other').strip() or 'other'
            if value in known_values:
                continue
            await db.execute(
                """
                INSERT OR IGNORE INTO item_categories(value, title, sort_order, created_at)
                VALUES (?, ?, 100, ?)
                """,
                (value, value, now_iso()),
            )


    async def _seed_suggested_shop_items(self, db: aiosqlite.Connection) -> dict[str, int]:
        """Add the ready-made shop item pack.

        This seed is intentionally idempotent. New catalog entries are added,
        while existing entries are left untouched so admin edits survive a
        restart or deployment.
        """
        category_values = await self._category_value_aliases(db)

        removed = 0
        for removed_name in REMOVED_ITEM_NAMES:
            cursor = await db.execute(
                'DELETE FROM shop_items WHERE lower(name) = lower(?)',
                (removed_name.strip(),),
            )
            removed += int(cursor.rowcount or 0)

        added = 0
        updated = 0
        for item in SUGGESTED_SHOP_ITEMS:
            name = str(item['name']).strip()
            description = str(item.get('description') or '').strip()
            price = max(0, int(item.get('price') or 0))
            rarity = str(item.get('rarity') or 'common').strip()
            stock = max(0, int(item.get('shop_quantity', 5)))
            is_active = 1 if item.get('is_active', True) else 0
            loot_chance_percent = min(100, max(0, int(item.get('loot_chance_percent', 0))))
            weight_kg = float(ITEM_WEIGHTS_KG.get(name, item.get('weight_kg', 0)) or 0)
            category_key = str(item.get('category') or 'other').strip()
            category = category_values.get(category_key) or category_values.get('other') or 'other'
            if 'is_consumable' in item:
                is_consumable = 1 if item.get('is_consumable') else 0
            else:
                is_consumable = 1 if infer_is_consumable(name, description, category) else 0
            if 'equipment_slot' in item:
                equipment_slot = str(item.get('equipment_slot') or '').strip()
            else:
                equipment_slot = infer_equipment_slot(name, description, category)
            carry_bonus_kg = float(item.get('carry_bonus_kg', infer_carry_bonus_kg(name, description, category)) or 0)
            speed_penalty = max(0, int(item.get('speed_penalty', infer_speed_penalty(name, description, category)) or 0))
            heal_hp = max(0, int(item.get('heal_hp', HEALING_ITEM_VALUES.get(name, 0)) or 0))
            sell_price = default_sell_price(price)

            cursor = await db.execute(
                'SELECT id FROM shop_items WHERE lower(name) = lower(?)',
                (name,),
            )
            row = await cursor.fetchone()
            if row:
                continue

            await db.execute(
                """
                INSERT INTO shop_items(
                    name, description, price, sell_price, rarity, category,
                    image_file_id, is_active, shop_quantity,
                    loot_chance_percent, weight_kg, is_consumable, equipment_slot,
                    carry_bonus_kg, speed_penalty, heal_hp, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    description,
                    price,
                    sell_price,
                    rarity,
                    category,
                    is_active,
                    stock,
                    loot_chance_percent,
                    weight_kg,
                    is_consumable,
                    equipment_slot,
                    carry_bonus_kg,
                    speed_penalty,
                    heal_hp,
                    now_iso(),
                ),
            )
            added += 1

        correction = await db.execute(
            'SELECT 1 FROM app_migrations WHERE name = ?',
            (CATALOG_CORRECTIONS_MIGRATION,),
        )
        if await correction.fetchone() is None:
            for name, category_key in ITEM_CATEGORY_CORRECTIONS.items():
                category = category_values.get(category_key) or category_values.get('other') or 'other'
                await db.execute(
                    """
                    UPDATE shop_items
                    SET category = ?, is_consumable = 0, equipment_slot = ?
                    WHERE lower(name) = lower(?)
                    """,
                    (category, infer_equipment_slot(name, '', category), name),
                )

            for name, heal_hp in HEALING_ITEM_VALUES.items():
                await db.execute(
                    """
                    UPDATE shop_items SET is_consumable = 1, heal_hp = ?
                    WHERE lower(name) = lower(?)
                    """,
                    (max(0, int(heal_hp)), name),
                )
            await db.execute(
                'INSERT INTO app_migrations(name, applied_at) VALUES (?, ?)',
                (CATALOG_CORRECTIONS_MIGRATION, now_iso()),
            )

        await db.execute(
            'INSERT OR REPLACE INTO app_migrations(name, applied_at) VALUES (?, ?)',
            (SUGGESTED_ITEMS_MIGRATION, now_iso()),
        )
        return {'added': added, 'updated': updated, 'removed': removed}


    async def _seed_character_shop_items(self, db: aiosqlite.Connection) -> None:
        """Install the requested character-focused catalog batch exactly once."""
        cursor = await db.execute(
            'SELECT 1 FROM app_migrations WHERE name = ?',
            (CHARACTER_ITEMS_MIGRATION,),
        )
        if await cursor.fetchone() is not None:
            return

        category_values = await self._category_value_aliases(db)
        for item in CHARACTER_SHOP_ITEMS:
            name = str(item['name']).strip()
            price = max(0, int(item['price']))
            category_key = str(item['category']).strip()
            category = category_values.get(category_key) or category_values.get('other') or 'other'
            values = (
                str(item['description']).strip(), price, default_sell_price(price),
                str(item['rarity']).strip(), category, 1,
                max(0, int(item['shop_quantity'])), float(item['weight_kg']),
                1 if item['is_consumable'] else 0, str(item['equipment_slot']).strip(),
            )
            existing = await (
                await db.execute('SELECT id FROM shop_items WHERE lower(name) = lower(?)', (name,))
            ).fetchone()
            if existing:
                await db.execute(
                    """
                    UPDATE shop_items
                    SET description = ?, price = ?, sell_price = ?, rarity = ?, category = ?,
                        is_active = ?, shop_quantity = ?, loot_chance_percent = 0,
                        weight_kg = ?, is_consumable = ?, equipment_slot = ?,
                        carry_bonus_kg = 0, speed_penalty = 0, heal_hp = 0
                    WHERE id = ?
                    """,
                    (*values, int(existing['id'])),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO shop_items(
                        name, description, price, sell_price, rarity, category,
                        image_file_id, is_active, shop_quantity, loot_chance_percent,
                        weight_kg, is_consumable, equipment_slot, carry_bonus_kg,
                        speed_penalty, heal_hp, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, 0, ?, ?, ?, 0, 0, 0, ?)
                    """,
                    (name, *values, now_iso()),
                )

        await db.execute(
            'INSERT INTO app_migrations(name, applied_at) VALUES (?, ?)',
            (CHARACTER_ITEMS_MIGRATION, now_iso()),
        )


    async def _assign_local_item_images(self, db: aiosqlite.Connection) -> dict[str, int]:
        """Assign bundled local images to known shop items.

        Works for both fresh installs and existing databases on the server.
        The bot can send either Telegram file_id values or local files from
        the project, for example assets/items/throwing_axe.png.
        """
        assigned = 0
        for name, image_path in ITEM_LOCAL_IMAGES.items():
            cursor = await db.execute(
                'SELECT id, image_file_id FROM shop_items WHERE lower(name) = lower(?)',
                (name,),
            )
            row = await cursor.fetchone()
            if not row:
                continue
            current_value = str(row['image_file_id'] or '').strip()
            if current_value == image_path:
                continue
            await db.execute(
                'UPDATE shop_items SET image_file_id = ? WHERE id = ?',
                (image_path, int(row['id'])),
            )
            assigned += 1

        await db.execute(
            'INSERT OR REPLACE INTO app_migrations(name, applied_at) VALUES (?, ?)',
            (ITEM_IMAGE_MIGRATION, now_iso()),
        )
        return {'assigned': assigned}


    @staticmethod
    def _infer_weight_kg(name: str, category: str | None = None) -> float:
        text = f'{name or ""} {category or ""}'.lower().replace('ё', 'е')
        if any(word in text for word in ('палатк',)):
            return 10.0
        if any(word in text for word in ('арбалет',)):
            return 8.0
        if any(word in text for word in ('доспех', 'броня', 'латы', 'кольчуг')):
            return 7.0
        if any(word in text for word in ('верев', 'веревк')):
            return 5.0
        if any(word in text for word in ('рюкзак', 'инструмент', 'набор алхим', 'набор лекар', 'набор картограф')):
            return 3.0
        if any(word in text for word in ('щит', 'лопат', 'молот')):
            return 2.5
        if any(word in text for word in ('меч', 'лук', 'топор', 'дубин', 'посох')):
            return 1.5
        if any(word in text for word in ('плащ', 'сумка', 'мешок', 'пояс')):
            return 1.0
        if any(word in text for word in ('еда', 'мяс', 'пирог', 'бутерброд', 'суп', 'лепеш', 'сухпаек', 'паек')):
            return 0.5
        if any(word in text for word in ('бутылк', 'фляг', 'кружк', 'вино', 'эль', 'кофе', 'чай', 'зель', 'склянк', 'флакон')):
            return 0.5
        if any(word in text for word in ('кинжал', 'дротик', 'свеч', 'сигнал', 'масло')):
            return 0.3
        if any(word in text for word in ('кристалл', 'камень', 'зеркал', 'порош', 'пыль')):
            return 0.2
        if any(word in text for word in ('свиток', 'кольц', 'монет', 'амулет', 'браслет', 'медальон', 'перстен')):
            return 0.1
        if any(word in text for word in ('болт', 'стрел')):
            return 0.05
        return 0.2

    async def _seed_item_weights(self, db: aiosqlite.Connection) -> dict[str, int]:
        """Set approximate item weights for bundled and old shop items."""
        updated = 0
        for name, weight in ITEM_WEIGHTS_KG.items():
            cursor = await db.execute(
                'UPDATE shop_items SET weight_kg = ? WHERE lower(name) = lower(?)',
                (float(weight), name),
            )
            updated += int(cursor.rowcount or 0)

        cursor = await db.execute(
            """
            SELECT id, name, COALESCE(category, 'other') AS category, COALESCE(weight_kg, 0) AS weight_kg
            FROM shop_items
            WHERE COALESCE(weight_kg, 0) <= 0
            """
        )
        rows = await cursor.fetchall()
        for row in rows:
            weight = self._infer_weight_kg(str(row['name'] or ''), str(row['category'] or 'other'))
            await db.execute('UPDATE shop_items SET weight_kg = ? WHERE id = ?', (weight, int(row['id'])))
            updated += 1

        await db.execute(
            'INSERT OR REPLACE INTO app_migrations(name, applied_at) VALUES (?, ?)',
            (ITEM_WEIGHT_MIGRATION, now_iso()),
        )
        return {'updated': updated}

    async def _seed_item_usage_flags(self, db: aiosqlite.Connection) -> dict[str, int]:
        """Infer consumables and equipment slots once for existing items."""
        migration_cursor = await db.execute('SELECT name FROM app_migrations WHERE name = ?', (ITEM_USAGE_MIGRATION,))
        if await migration_cursor.fetchone():
            return {'updated': 0}

        updated = 0
        suggested_items = {str(item['name']).strip().casefold(): item for item in SUGGESTED_SHOP_ITEMS}
        cursor = await db.execute(
            """
            SELECT id, name, description, COALESCE(category, 'other') AS category
            FROM shop_items
            """
        )
        rows = await cursor.fetchall()
        for row in rows:
            name = str(row['name'] or '')
            description = str(row['description'] or '')
            category = str(row['category'] or 'other')
            suggested_item = suggested_items.get(name.strip().casefold())
            if suggested_item and 'is_consumable' in suggested_item:
                is_consumable = 1 if suggested_item.get('is_consumable') else 0
            else:
                is_consumable = 1 if infer_is_consumable(name, description, category) else 0
            if suggested_item and 'equipment_slot' in suggested_item:
                equipment_slot = str(suggested_item.get('equipment_slot') or '').strip()
            else:
                equipment_slot = infer_equipment_slot(name, description, category)
            await db.execute(
                """
                UPDATE shop_items
                SET is_consumable = ?, equipment_slot = ?
                WHERE id = ?
                """,
                (
                    is_consumable,
                    equipment_slot,
                    int(row['id']),
                ),
            )
            updated += 1

        await db.execute(
            'INSERT OR REPLACE INTO app_migrations(name, applied_at) VALUES (?, ?)',
            (ITEM_USAGE_MIGRATION, now_iso()),
        )
        return {'updated': updated}

    async def _seed_item_sell_prices(self, db: aiosqlite.Connection) -> dict[str, int]:
        """Give existing items a default sell price: 80% of purchase price."""
        migration_cursor = await db.execute('SELECT name FROM app_migrations WHERE name = ?', (ITEM_SELL_PRICE_MIGRATION,))
        if await migration_cursor.fetchone():
            return {'updated': 0}

        cursor = await db.execute(
            """
            SELECT id, COALESCE(price, 0) AS price
            FROM shop_items
            WHERE COALESCE(sell_price, 0) <= 0
            """
        )
        rows = await cursor.fetchall()
        updated = 0
        for row in rows:
            await db.execute(
                'UPDATE shop_items SET sell_price = ? WHERE id = ?',
                (default_sell_price(int(row['price'] or 0)), int(row['id'])),
            )
            updated += 1

        await db.execute(
            'INSERT OR REPLACE INTO app_migrations(name, applied_at) VALUES (?, ?)',
            (ITEM_SELL_PRICE_MIGRATION, now_iso()),
        )
        return {'updated': updated}

    async def _seed_carry_container_stats(self, db: aiosqlite.Connection) -> dict[str, int]:
        """Infer carry capacity bonuses for bags and backpacks once."""
        migration_cursor = await db.execute('SELECT name FROM app_migrations WHERE name = ?', (ITEM_CARRY_CONTAINER_MIGRATION,))
        if await migration_cursor.fetchone():
            return {'updated': 0}

        cursor = await db.execute(
            """
            SELECT id, name, description, COALESCE(category, 'other') AS category
            FROM shop_items
            """
        )
        rows = await cursor.fetchall()
        updated = 0
        for row in rows:
            name = str(row['name'] or '')
            description = str(row['description'] or '')
            category = str(row['category'] or 'other')
            carry_bonus_kg = infer_carry_bonus_kg(name, description, category)
            speed_penalty = infer_speed_penalty(name, description, category)
            if carry_bonus_kg <= 0 and speed_penalty <= 0:
                continue
            await db.execute(
                """
                UPDATE shop_items
                SET equipment_slot = 'container',
                    carry_bonus_kg = CASE WHEN COALESCE(carry_bonus_kg, 0) <= 0 THEN ? ELSE carry_bonus_kg END,
                    speed_penalty = CASE WHEN COALESCE(speed_penalty, 0) <= 0 THEN ? ELSE speed_penalty END
                WHERE id = ?
                """,
                (carry_bonus_kg, speed_penalty, int(row['id'])),
            )
            updated += 1

        await db.execute(
            'INSERT OR REPLACE INTO app_migrations(name, applied_at) VALUES (?, ?)',
            (ITEM_CARRY_CONTAINER_MIGRATION, now_iso()),
        )
        return {'updated': updated}

    async def _category_value_aliases(self, db: aiosqlite.Connection) -> dict[str, str]:
        cursor = await db.execute('SELECT value, title FROM item_categories')
        rows = await cursor.fetchall()
        categories = [(str(row['value']), str(row['title']).lower()) for row in rows]

        def find(default_value: str, title_keywords: list[str]) -> str:
            for value, _ in categories:
                if value == default_value:
                    return value
            for value, title in categories:
                haystack = f'{value.lower()} {title}'
                if any(keyword in haystack for keyword in title_keywords):
                    return value
            return 'other'

        return {
            'weapon': find('weapon', ['оруж', 'weapon']),
            'armor': find('armor', ['брон', 'доспех', 'armor']),
            'food': find('food', ['еда', 'food']),
            'drink': find('drink', ['пить', 'напит', 'drink']),
            'magic': find('magic', ['маг', 'magic']),
            'tools': find('tools', ['инструмент', 'tools']),
            'consumable': find('consumable', ['расход', 'consumable']),
            'gear': find('gear', ['снаряж', 'gear']),
            'accessory': find('accessory', ['аксессуар', 'украшен', 'accessor']),
            'other': find('other', ['другое', 'other']),
        }

    @staticmethod
    def _text_has_any(text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _infer_item_category(self, name: str, description: str, category_values: dict[str, str], current_category: str = 'other') -> str:
        text = f'{name} {description}'.lower().replace('ё', 'е')

        def category(key: str) -> str:
            return category_values.get(key) or category_values.get('other') or 'other'

        # Важен порядок: кольцо лучше отправить в аксессуары, а не в магию.
        if self._text_has_any(text, ('кольц', 'ожерел', 'амулет', 'талисман', 'браслет', 'кулон', 'перстен', 'цепочк', 'бусы')):
            return category('accessory')
        if self._text_has_any(text, ('брон', 'доспех', 'щит', 'шлем', 'латы', 'кольчуг')):
            return category('armor')
        if self._text_has_any(text, ('бутерброд', 'блин', 'лепеш', 'еда', 'сухпаек', 'паек', 'мяс', 'медов', 'медом', 'хлеб', 'сыр', 'пирог')):
            return category('food')
        if self._text_has_any(text, ('зель', 'свиток', 'болт', 'стрел', 'шашк', 'гранат', 'флакон', 'свят', 'яд', 'снотвор', 'расход')):
            return category('consumable')
        if self._text_has_any(text, ('вино', 'эль', 'пиво', 'кофе', 'чай', 'напит', 'кружк', 'бутылк')):
            return category('drink')
        if self._text_has_any(text, ('инструмент', 'отмыч', 'воровск', 'ремеслен', 'гончар', 'рыбац', 'набор для записи', 'перо', 'чернил', 'лупа')):
            return category('tools')
        if self._text_has_any(text, ('меч', 'кинжал', 'лук', 'арбалет', 'дубин', 'молот', 'клин', 'дротик', 'копье', 'топор', 'оруж')):
            return category('weapon')
        if self._text_has_any(text, ('маг', 'кристалл', 'плащ лича', 'волшеб', 'артефакт', 'заклинан', 'руна', 'лич', 'жертвопринош')):
            return category('magic')
        if self._text_has_any(text, ('верев', 'веревк', 'палатк', 'спальник', 'спальный', 'рюкзак', 'мешок', 'лопат', 'крюк', 'огниво', 'ламп', 'фонар', 'фляг', 'свисток', 'снаряж')):
            return category('gear')

        if current_category and current_category != 'other':
            return current_category
        return category('other')

    async def _auto_categorize_existing_items(self, db: aiosqlite.Connection, force: bool = False) -> dict[str, Any]:
        if not force:
            cursor = await db.execute('SELECT name FROM app_migrations WHERE name = ?', (AUTO_CATEGORIZE_MIGRATION,))
            if await cursor.fetchone():
                return {'changed': 0, 'by_category': {}}

        category_values = await self._category_value_aliases(db)
        cursor = await db.execute('SELECT id, name, description, COALESCE(category, \'other\') AS category FROM shop_items')
        rows = await cursor.fetchall()

        changed = 0
        by_category: dict[str, int] = {}
        for row in rows:
            current_category = str(row['category'] or 'other')
            new_category = self._infer_item_category(
                str(row['name'] or ''),
                str(row['description'] or ''),
                category_values,
                current_category,
            )
            if new_category != current_category:
                await db.execute('UPDATE shop_items SET category = ? WHERE id = ?', (new_category, int(row['id'])))
                changed += 1
                by_category[new_category] = by_category.get(new_category, 0) + 1

        if not force:
            await db.execute(
                'INSERT OR REPLACE INTO app_migrations(name, applied_at) VALUES (?, ?)',
                (AUTO_CATEGORIZE_MIGRATION, now_iso()),
            )
        return {'changed': changed, 'by_category': by_category}

    async def auto_categorize_items(self) -> dict[str, Any]:
        async with self.connect() as db:
            result = await self._auto_categorize_existing_items(db, force=True)
            await db.commit()
            return result

    async def list_categories(
        self,
        only_with_items: bool = False,
        only_active: bool = False,
        only_purchasable: bool = False,
    ) -> list[dict[str, Any]]:
        query = 'SELECT ic.* FROM item_categories ic'
        conditions: list[str] = []
        params: list[Any] = []
        if only_with_items or only_active or only_purchasable:
            query += ' WHERE EXISTS (SELECT 1 FROM shop_items si WHERE COALESCE(si.category, \'other\') = ic.value'
            if only_active or only_purchasable:
                query += ' AND si.is_active = 1'
            if only_purchasable:
                query += ' AND si.shop_quantity != 0'
            query += ')'
        query += ' ORDER BY ic.sort_order ASC, ic.title COLLATE NOCASE ASC'
        async with self.connect() as db:
            cursor = await db.execute(query, tuple(params))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_category(self, value: str) -> dict[str, Any] | None:
        async with self.connect() as db:
            cursor = await db.execute('SELECT * FROM item_categories WHERE value = ?', ((value or 'other').strip(),))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_category(self, title: str) -> dict[str, Any]:
        clean_title = title.strip()
        if len(clean_title) < 2:
            raise ValueError('Название категории должно быть минимум 2 символа.')
        async with self.connect() as db:
            exists_cursor = await db.execute('SELECT * FROM item_categories WHERE title = ?', (clean_title,))
            exists = await exists_cursor.fetchone()
            if exists:
                raise ValueError('Такая категория уже есть.')

            temp_value = f'tmp_{int(datetime.now(timezone.utc).timestamp() * 1000)}'
            cursor = await db.execute(
                """
                INSERT INTO item_categories(value, title, sort_order, created_at)
                VALUES (?, ?, 100, ?)
                """,
                (temp_value, clean_title, now_iso()),
            )
            category_id = int(cursor.lastrowid)
            value = f'cat_{category_id}'
            await db.execute('UPDATE item_categories SET value = ? WHERE id = ?', (value, category_id))
            await db.commit()

            updated_cursor = await db.execute('SELECT * FROM item_categories WHERE id = ?', (category_id,))
            row = await updated_cursor.fetchone()
            return dict(row)

    async def delete_category(self, value: str) -> tuple[bool, str]:
        value = (value or '').strip()
        if value in {category_value for category_value, _ in DEFAULT_ITEM_CATEGORIES}:
            return False, 'Стандартную категорию удалять нельзя.'
        async with self.connect() as db:
            items_cursor = await db.execute('SELECT COUNT(*) AS count FROM shop_items WHERE COALESCE(category, \'other\') = ?', (value,))
            items_count = int((await items_cursor.fetchone())['count'])
            if items_count > 0:
                return False, f'В категории есть предметы: {items_count}. Сначала перенеси их в другую категорию.'
            await db.execute('DELETE FROM item_categories WHERE value = ?', (value,))
            await db.commit()
            return True, 'Категория удалена.'

    async def count_items(
        self,
        only_active: bool = True,
        category: str | None = None,
        only_purchasable: bool = False,
    ) -> int:
        query = 'SELECT COUNT(*) AS count FROM shop_items'
        conditions: list[str] = []
        params: list[Any] = []
        if only_active or only_purchasable:
            conditions.append('is_active = 1')
        if only_purchasable:
            conditions.append('shop_quantity != 0')
        if category and category != 'all':
            conditions.append("COALESCE(category, 'other') = ?")
            params.append(category)
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        async with self.connect() as db:
            cursor = await db.execute(query, tuple(params))
            row = await cursor.fetchone()
            return int(row['count'])

    async def _check_login_lock(self, db: aiosqlite.Connection, telegram_id: int) -> None:
        cursor = await db.execute(
            'SELECT failed_count, locked_until FROM auth_attempts WHERE telegram_id = ?',
            (telegram_id,),
        )
        row = await cursor.fetchone()
        if row is None or not row['locked_until']:
            return
        try:
            locked_until = datetime.fromisoformat(str(row['locked_until']))
        except ValueError:
            locked_until = datetime.now(timezone.utc)
        now = datetime.now(timezone.utc)
        if locked_until > now:
            seconds = max(1, int((locked_until - now).total_seconds()))
            minutes = max(1, (seconds + 59) // 60)
            raise PermissionError(f'Слишком много неудачных попыток входа. Попробуй через {minutes} мин.')
        await db.execute('DELETE FROM auth_attempts WHERE telegram_id = ?', (telegram_id,))

    async def _record_failed_login(self, db: aiosqlite.Connection, telegram_id: int) -> None:
        cursor = await db.execute(
            'SELECT failed_count FROM auth_attempts WHERE telegram_id = ?',
            (telegram_id,),
        )
        row = await cursor.fetchone()
        failed_count = int(row['failed_count'] or 0) + 1 if row else 1
        locked_until = None
        if failed_count >= LOGIN_MAX_FAILED_ATTEMPTS:
            locked_until = (datetime.now(timezone.utc) + timedelta(minutes=LOGIN_LOCK_MINUTES)).isoformat(timespec='seconds')
        await db.execute(
            """
            INSERT INTO auth_attempts(telegram_id, failed_count, first_failed_at, locked_until)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                failed_count = excluded.failed_count,
                locked_until = excluded.locked_until
            """,
            (telegram_id, failed_count, now_iso(), locked_until),
        )

    async def create_character(self, login: str, password: str, display_name: str) -> int:
        clean_login = str(login or '').strip()
        clean_password = str(password or '').strip()
        clean_display_name = str(display_name or '').strip()
        if len(clean_login) < 3:
            raise ValueError('Логин должен быть минимум 3 символа.')
        if len(clean_password) < 6:
            raise ValueError('Пароль должен быть минимум 6 символов.')
        if not clean_display_name:
            raise ValueError('Имя персонажа не может быть пустым.')
        salt, password_hash = create_password_hash(clean_password)
        async with self.connect() as db:
            default_cursor = await db.execute('SELECT id FROM game_sessions ORDER BY id ASC LIMIT 1')
            default_session = await default_cursor.fetchone()
            session_id = int(default_session['id']) if default_session else await self._ensure_default_session(db)
            cursor = await db.execute(
                """
                INSERT INTO characters(login, password_salt, password_hash, display_name, session_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (clean_login, salt, password_hash, clean_display_name, session_id, now_iso()),
            )
            character_id = int(cursor.lastrowid)
            await self._add_journal_entry(db, character_id, 'character_created', 'Персонаж создан', 'Персонаж появился в кампании.')
            await db.commit()
            return character_id

    async def authenticate_character(self, login: str, password: str, telegram_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            await self._check_login_lock(db, telegram_id)
            cursor = await db.execute(
                'SELECT * FROM characters WHERE login = ?',
                (login.strip(),),
            )
            row = await cursor.fetchone()
            if row is None:
                await self._record_failed_login(db, telegram_id)
                await db.commit()
                return None
            if not verify_password(password, row['password_salt'], row['password_hash']):
                await self._record_failed_login(db, telegram_id)
                await db.commit()
                return None
            if row['telegram_id'] is not None and row['telegram_id'] != telegram_id:
                raise PermissionError('Этот персонаж уже привязан к другому Telegram аккаунту.')
            await db.execute(
                'UPDATE characters SET telegram_id = ?, last_login_at = ? WHERE id = ?',
                (telegram_id, now_iso(), row['id']),
            )
            await db.execute('DELETE FROM auth_attempts WHERE telegram_id = ?', (telegram_id,))
            await db.commit()
            updated = await db.execute(
                """
                SELECT c.*, gs.title AS session_title
                FROM characters c
                LEFT JOIN game_sessions gs ON gs.id = c.session_id
                WHERE c.id = ?
                """,
                (row['id'],),
            )
            updated_row = await updated.fetchone()
            return enrich_character(dict(updated_row))

    async def unlink_character(self, telegram_id: int) -> None:
        async with self.connect() as db:
            await db.execute('UPDATE characters SET telegram_id = NULL WHERE telegram_id = ?', (telegram_id,))
            await db.commit()

    async def get_character_by_telegram_id(self, telegram_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT c.*, gs.title AS session_title
                FROM characters c
                LEFT JOIN game_sessions gs ON gs.id = c.session_id
                WHERE c.telegram_id = ?
                """,
                (telegram_id,),
            )
            row = await cursor.fetchone()
            return enrich_character(dict(row)) if row else None

    async def get_character(self, character_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT c.*, gs.title AS session_title
                FROM characters c
                LEFT JOIN game_sessions gs ON gs.id = c.session_id
                WHERE c.id = ?
                """,
                (character_id,),
            )
            row = await cursor.fetchone()
            return enrich_character(dict(row)) if row else None

    async def list_characters(self, session_id: int | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT c.*, gs.title AS session_title
            FROM characters c
            LEFT JOIN game_sessions gs ON gs.id = c.session_id
        """
        params: list[Any] = []
        if session_id is not None:
            query += ' WHERE c.session_id = ?'
            params.append(session_id)
        query += ' ORDER BY COALESCE(gs.title, \'Без сессии\') COLLATE NOCASE ASC, c.display_name COLLATE NOCASE ASC'
        async with self.connect() as db:
            cursor = await db.execute(query, tuple(params))
            rows = await cursor.fetchall()
            return [enrich_character(dict(row)) for row in rows]

    async def import_character_sheet(self, sheet: dict[str, Any], password: str) -> dict[str, Any]:
        clean_password = str(password or '').strip()
        if not clean_password:
            raise ValueError('Временный пароль не может быть пустым.')
        salt, password_hash = create_password_hash(clean_password)
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            await db.execute(
                """
                INSERT OR IGNORE INTO game_sessions(title, description, is_active, created_at)
                VALUES (?, ?, 1, ?)
                """,
                (
                    sheet['session_title'],
                    f'Автоматически создана для группы {sheet["session_number"]}.',
                    now_iso(),
                ),
            )
            session_row = await (
                await db.execute('SELECT id FROM game_sessions WHERE title = ?', (sheet['session_title'],))
            ).fetchone()
            session_id = int(session_row['id'])

            row = await (
                await db.execute(
                    'SELECT id FROM characters WHERE login = ? OR display_name = ? ORDER BY id LIMIT 1',
                    (sheet['login'], sheet['display_name']),
                )
            ).fetchone()
            created = row is None
            if created:
                cursor = await db.execute(
                    """
                    INSERT INTO characters(
                        login, password_salt, password_hash, display_name, xp, gold,
                        session_id, strength_score, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sheet['login'], salt, password_hash, sheet['display_name'],
                        int(sheet.get('xp') or 0), int(sheet.get('gold') or 0), session_id,
                        int(sheet.get('strength_score') or 10), now_iso(),
                    ),
                )
                character_id = int(cursor.lastrowid)
            else:
                character_id = int(row['id'])
                await db.execute(
                    """
                    UPDATE characters
                    SET login = ?, password_salt = ?, password_hash = ?, display_name = ?,
                        xp = ?, gold = ?, session_id = ?, strength_score = ?
                    WHERE id = ?
                    """,
                    (
                        sheet['login'], salt, password_hash, sheet['display_name'],
                        int(sheet.get('xp') or 0), int(sheet.get('gold') or 0), session_id,
                        int(sheet.get('strength_score') or 10), character_id,
                    ),
                )

            await db.execute(
                """
                INSERT INTO character_sheets(
                    character_id, player_name, class_name, subclass_name, race_name,
                    background_name, alignment, level, source_name, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(character_id) DO UPDATE SET
                    player_name = excluded.player_name,
                    class_name = excluded.class_name,
                    subclass_name = excluded.subclass_name,
                    race_name = excluded.race_name,
                    background_name = excluded.background_name,
                    alignment = excluded.alignment,
                    level = excluded.level,
                    source_name = excluded.source_name,
                    imported_at = excluded.imported_at
                """,
                (
                    character_id, sheet.get('player_name', ''), sheet.get('class_name', ''),
                    sheet.get('subclass_name', ''), sheet.get('race_name', ''),
                    sheet.get('background_name', ''), sheet.get('alignment', ''),
                    int(sheet.get('level') or 1), sheet.get('source_name', ''), now_iso(),
                ),
            )
            await db.execute('DELETE FROM character_sheet_entries WHERE character_id = ?', (character_id,))
            await db.executemany(
                """
                INSERT INTO character_sheet_entries(
                    character_id, section, name, description, source_id, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        character_id, entry['section'], entry['name'], entry.get('description', ''),
                        entry.get('source_id', ''), int(entry.get('sort_order') or 0),
                    )
                    for entry in sheet.get('entries', [])
                ],
            )
            await self._add_journal_entry(
                db,
                character_id,
                'sheet_imported',
                'Лист персонажа импортирован',
                f'Источник: {sheet.get("source_name", "Long Story Short")}.',
            )
            await db.commit()
        return {
            'character_id': character_id,
            'created': created,
            'login': sheet['login'],
            'display_name': sheet['display_name'],
            'session_id': session_id,
            'session_title': sheet['session_title'],
            'entries_count': len(sheet.get('entries', [])),
        }

    async def get_character_sheet(self, character_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            row = await (
                await db.execute('SELECT * FROM character_sheets WHERE character_id = ?', (character_id,))
            ).fetchone()
            if row is None:
                return None
            counts = await (
                await db.execute(
                    """
                    SELECT section, COUNT(*) AS count
                    FROM character_sheet_entries
                    WHERE character_id = ?
                    GROUP BY section
                    """,
                    (character_id,),
                )
            ).fetchall()
            result = dict(row)
            result['section_counts'] = {item['section']: int(item['count']) for item in counts}
            return result

    async def list_character_sheet_entries(self, character_id: int, section: str) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await (
                await db.execute(
                    """
                    SELECT * FROM character_sheet_entries
                    WHERE character_id = ? AND section = ?
                    ORDER BY sort_order, name COLLATE NOCASE
                    """,
                    (character_id, section),
                )
            ).fetchall()
            return [dict(row) for row in rows]

    async def get_character_sheet_entry(self, character_id: int, entry_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            row = await (
                await db.execute(
                    'SELECT * FROM character_sheet_entries WHERE character_id = ? AND id = ?',
                    (character_id, entry_id),
                )
            ).fetchone()
            return dict(row) if row else None

    async def list_session_recipients(self, session_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT c.id, c.display_name, c.telegram_id, gs.title AS session_title
                FROM characters c
                LEFT JOIN game_sessions gs ON gs.id = c.session_id
                WHERE c.session_id = ? AND c.telegram_id IS NOT NULL
                ORDER BY c.display_name COLLATE NOCASE ASC
                """,
                (session_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def list_character_journal(self, character_id: int, limit: int = 15) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM character_journal
                WHERE character_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (character_id, max(1, int(limit))),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def list_character_conditions(self, character_id: int) -> list[str]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT condition
                FROM character_conditions
                WHERE character_id = ?
                ORDER BY added_at ASC, condition ASC
                """,
                (character_id,),
            )
            return [str(row['condition']) for row in await cursor.fetchall()]

    async def toggle_character_condition(
        self,
        character_id: int,
        condition: str,
        admin_telegram_id: int | None = None,
    ) -> tuple[bool, str]:
        clean_condition = str(condition or '').strip()
        if clean_condition not in CONDITION_LABELS:
            return False, 'Неизвестное состояние.'
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            character_cursor = await db.execute('SELECT display_name FROM characters WHERE id = ?', (character_id,))
            character = await character_cursor.fetchone()
            if character is None:
                return False, 'Персонаж не найден.'
            existing_cursor = await db.execute(
                'SELECT 1 FROM character_conditions WHERE character_id = ? AND condition = ?',
                (character_id, clean_condition),
            )
            existing = await existing_cursor.fetchone()
            label = CONDITION_LABELS[clean_condition]
            if existing:
                await db.execute(
                    'DELETE FROM character_conditions WHERE character_id = ? AND condition = ?',
                    (character_id, clean_condition),
                )
                action = 'снято'
                event_type = 'condition_removed'
            else:
                await db.execute(
                    'INSERT INTO character_conditions(character_id, condition, added_at) VALUES (?, ?, ?)',
                    (character_id, clean_condition, now_iso()),
                )
                action = 'добавлено'
                event_type = 'condition_added'
            await self._add_journal_entry(
                db,
                character_id,
                event_type,
                f'Состояние: {label}',
                f'Состояние {action}.',
                admin_telegram_id,
            )
            await db.commit()
            return True, f'{label}: {action}.'

    async def toggle_character_inspiration(
        self,
        character_id: int,
        admin_telegram_id: int | None = None,
    ) -> tuple[bool, str]:
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            cursor = await db.execute(
                'SELECT display_name, COALESCE(inspiration, 0) AS inspiration FROM characters WHERE id = ?',
                (character_id,),
            )
            character = await cursor.fetchone()
            if character is None:
                return False, 'Персонаж не найден.'
            new_value = 0 if int(character['inspiration']) else 1
            await db.execute('UPDATE characters SET inspiration = ? WHERE id = ?', (new_value, character_id))
            title = 'Вдохновение получено' if new_value else 'Вдохновение снято'
            await self._add_journal_entry(db, character_id, 'inspiration', title, '', admin_telegram_id)
            await db.commit()
            state = 'есть' if new_value else 'нет'
            return True, f'Вдохновение у {character["display_name"]}: {state}.'

    async def spend_inspiration(self, character_id: int) -> tuple[bool, str]:
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            cursor = await db.execute(
                'UPDATE characters SET inspiration = 0 WHERE id = ? AND inspiration = 1',
                (character_id,),
            )
            if int(cursor.rowcount or 0) <= 0:
                return False, 'У персонажа сейчас нет вдохновения.'
            await self._add_journal_entry(
                db,
                character_id,
                'inspiration_spent',
                'Вдохновение использовано',
                'Игрок использовал вдохновение.',
            )
            await db.commit()
            return True, 'Вдохновение использовано.'

    async def update_character_notes(
        self,
        character_id: int,
        notes: str,
        admin_telegram_id: int | None = None,
    ) -> tuple[bool, str]:
        clean_notes = str(notes or '').strip()
        async with self.connect() as db:
            cursor = await db.execute(
                'UPDATE characters SET admin_notes = ? WHERE id = ?',
                (clean_notes, character_id),
            )
            if int(cursor.rowcount or 0) <= 0:
                await db.commit()
                return False, 'Персонаж не найден.'
            await self._add_journal_entry(
                db,
                character_id,
                'admin_notes',
                'Заметки мастера обновлены',
                'Скрытая заметка мастера изменена.',
                admin_telegram_id,
            )
            await db.commit()
            return True, 'Заметки мастера обновлены.'

    async def apply_session_rest(
        self,
        session_id: int,
        rest_type: str,
        hp_restore: int | None = None,
        note: str | None = None,
        admin_telegram_id: int | None = None,
    ) -> tuple[bool, str]:
        clean_type = str(rest_type or '').strip()
        if clean_type not in {'short', 'long'}:
            return False, 'Неизвестный тип отдыха.'

        clean_note = str(note or '').strip()
        restore_value = max(0, int(hp_restore or 0))
        if clean_type == 'short' and restore_value <= 0:
            return False, 'Для короткого отдыха нужно указать, сколько HP восстановить.'

        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            session_cursor = await db.execute('SELECT title FROM game_sessions WHERE id = ?', (session_id,))
            session = await session_cursor.fetchone()
            if session is None:
                return False, 'Сессия не найдена.'

            characters_cursor = await db.execute(
                """
                SELECT id, display_name, COALESCE(hp, 10) AS hp, COALESCE(max_hp, 10) AS max_hp
                FROM characters
                WHERE session_id = ?
                ORDER BY display_name COLLATE NOCASE ASC
                """,
                (session_id,),
            )
            characters = await characters_cursor.fetchall()
            if not characters:
                return False, 'В этой сессии нет персонажей.'

            total_restored = 0
            changed = 0
            for character in characters:
                character_id = int(character['id'])
                before_hp = max(0, int(character['hp'] or 0))
                max_hp = max(1, int(character['max_hp'] or 10))
                if clean_type == 'long':
                    after_hp = max_hp
                    title = 'Долгий отдых'
                    details = f'HP восстановлены до максимума: {after_hp}/{max_hp}.'
                else:
                    after_hp = min(max_hp, before_hp + restore_value)
                    title = 'Короткий отдых'
                    details = f'Восстановлено {after_hp - before_hp} HP: {before_hp}/{max_hp} → {after_hp}/{max_hp}.'

                if clean_note:
                    details += f'\nЗаметка мастера: {clean_note}'

                await db.execute('UPDATE characters SET hp = ? WHERE id = ?', (after_hp, character_id))
                if after_hp > 0:
                    await db.execute(
                        'UPDATE characters SET death_save_successes = 0, death_save_failures = 0 WHERE id = ?',
                        (character_id,),
                    )
                await self._add_journal_entry(db, character_id, clean_type + '_rest', title, details, admin_telegram_id)
                total_restored += max(0, after_hp - before_hp)
                if after_hp != before_hp:
                    changed += 1

            character_ids = [int(character['id']) for character in characters]
            placeholders = ','.join('?' for _ in character_ids)
            await db.execute(
                f"DELETE FROM character_conditions WHERE duration_kind = 'rest' AND character_id IN ({placeholders})",
                tuple(character_ids),
            )

            await db.commit()

            names = ', '.join(character['display_name'] for character in characters)
            if clean_type == 'long':
                result = f'Долгий отдых применён для сессии «{session["title"]}». HP восстановлены до максимума.'
            else:
                result = f'Короткий отдых применён для сессии «{session["title"]}». Всего восстановлено {total_restored} HP.'
            return True, result + f'\nПерсонажи: {names}\nИзменилось HP у: {changed}'


    async def delete_character(self, character_id: int) -> tuple[bool, str]:
        async with self.connect() as db:
            cursor = await db.execute('SELECT display_name FROM characters WHERE id = ?', (character_id,))
            row = await cursor.fetchone()
            if row is None:
                return False, 'Персонаж не найден.'
            await db.execute('DELETE FROM characters WHERE id = ?', (character_id,))
            await db.commit()
            return True, f'Персонаж {row["display_name"]} удалён.'

    async def update_character_field(self, character_id: int, field: str, value: Any) -> tuple[bool, str]:
        allowed_fields = {
            'display_name', 'login', 'xp', 'gold', 'hp', 'max_hp',
            'strength_score', 'max_carry_kg', 'initiative_bonus',
        }
        if field not in allowed_fields:
            return False, 'Это поле персонажа нельзя редактировать.'
        if field in {'display_name', 'login'}:
            value = str(value).strip()
            if not value:
                return False, 'Значение не может быть пустым.'
            if field == 'login' and len(value) < 3:
                return False, 'Логин должен быть минимум 3 символа.'
        elif field in {'xp', 'gold', 'hp', 'max_hp'}:
            try:
                value = max(0, int(value))
            except (TypeError, ValueError):
                return False, 'Нужно целое число.'
            if field == 'max_hp':
                value = max(1, value)
        elif field == 'strength_score':
            try:
                value = min(30, max(1, int(value)))
            except (TypeError, ValueError):
                return False, 'Сила должна быть числом от 1 до 30.'
        elif field == 'initiative_bonus':
            try:
                value = min(30, max(-30, int(value)))
            except (TypeError, ValueError):
                return False, 'Бонус инициативы должен быть целым числом от -30 до 30.'
        elif field == 'max_carry_kg':
            raw = str(value).strip().replace(',', '.')
            if raw in {'', '0', 'auto', 'авто', '-'}:
                value = None
            else:
                try:
                    value = max(0.1, float(raw))
                except (TypeError, ValueError):
                    return False, 'Грузоподъёмность нужно ввести числом в кг или словом авто.'
        async with self.connect() as db:
            try:
                if field == 'max_hp':
                    cursor = await db.execute(
                        'UPDATE characters SET max_hp = ?, hp = MIN(hp, ?) WHERE id = ?',
                        (value, value, character_id),
                    )
                elif field == 'hp':
                    cursor = await db.execute(
                        'UPDATE characters SET hp = MIN(?, max_hp) WHERE id = ?',
                        (value, character_id),
                    )
                    if value > 0:
                        await db.execute(
                            'UPDATE characters SET death_save_successes = 0, death_save_failures = 0 WHERE id = ?',
                            (character_id,),
                        )
                else:
                    cursor = await db.execute(f'UPDATE characters SET {field} = ? WHERE id = ?', (value, character_id))
                if int(cursor.rowcount or 0) > 0:
                    labels = {
                        'display_name': 'имя',
                        'login': 'логин',
                        'xp': 'XP',
                        'gold': 'монеты',
                        'hp': 'HP',
                        'max_hp': 'максимум HP',
                        'strength_score': 'Сила',
                        'max_carry_kg': 'лимит веса',
                        'initiative_bonus': 'бонус инициативы',
                    }
                    await self._add_journal_entry(
                        db,
                        character_id,
                        'character_updated',
                        'Данные персонажа обновлены',
                        f'Администратор изменил поле: {labels.get(field, field)}.',
                    )
                await db.commit()
            except sqlite3.IntegrityError:
                if field == 'login':
                    return False, 'Такой логин уже занят. Введи другой логин.'
                return False, 'Не получилось обновить поле: значение конфликтует с уже существующими данными.'
            except Exception as exc:
                return False, f'Не получилось обновить поле. Ошибка: {exc}'
            if cursor.rowcount == 0:
                return False, 'Персонаж не найден.'
            return True, 'Данные персонажа обновлены.'

    async def update_character_password(self, character_id: int, password: str) -> tuple[bool, str]:
        password = str(password).strip()
        if len(password) < 6:
            return False, 'Пароль должен быть минимум 6 символов.'
        salt, password_hash = create_password_hash(password)
        async with self.connect() as db:
            cursor = await db.execute(
                'UPDATE characters SET password_salt = ?, password_hash = ? WHERE id = ?',
                (salt, password_hash, character_id),
            )
            await db.commit()
            if cursor.rowcount == 0:
                return False, 'Персонаж не найден.'
            await self._add_journal_entry(db, character_id, 'password_updated', 'Пароль обновлён', 'Администратор обновил пароль персонажа.')
            await db.commit()
            return True, 'Пароль персонажа обновлён.'

    async def get_inventory_weight(self, character_id: int) -> float:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT COALESCE(SUM(i.quantity * COALESCE(si.weight_kg, 0)), 0) AS total_weight
                FROM inventory i
                JOIN shop_items si ON si.id = i.item_id
                WHERE i.character_id = ? AND i.quantity > 0
                """,
                (character_id,),
            )
            row = await cursor.fetchone()
            return round(float(row['total_weight'] or 0), 2)

    async def get_character_carry_info(self, character_id: int) -> dict[str, Any] | None:
        character = await self.get_character(character_id)
        if character is None:
            return None
        current_weight = await self.get_inventory_weight(character_id)
        strength = int(character.get('strength_score') or DEFAULT_STRENGTH_SCORE)
        custom_capacity = character.get('max_carry_kg')
        base_weight = float(custom_capacity) if custom_capacity is not None else carry_capacity_from_strength(strength)
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT COALESCE(SUM(COALESCE(si.carry_bonus_kg, 0)), 0) AS carry_bonus_kg,
                       COALESCE(SUM(COALESCE(si.speed_penalty, 0)), 0) AS speed_penalty
                FROM character_equipment ce
                JOIN shop_items si ON si.id = ce.item_id
                JOIN inventory i ON i.character_id = ce.character_id AND i.item_id = ce.item_id AND i.quantity > 0
                WHERE ce.character_id = ?
                """,
                (character_id,),
            )
            equipment_stats = await cursor.fetchone()
        carry_bonus_kg = float(equipment_stats['carry_bonus_kg'] or 0) if equipment_stats else 0.0
        speed_penalty = int(equipment_stats['speed_penalty'] or 0) if equipment_stats else 0
        max_weight = base_weight + carry_bonus_kg
        return {
            'character_id': character_id,
            'strength_score': strength,
            'base_carry_kg': round(base_weight, 1),
            'carry_bonus_kg': round(carry_bonus_kg, 1),
            'speed_penalty': speed_penalty,
            'max_carry_kg': round(max_weight, 1),
            'current_weight_kg': round(current_weight, 2),
            'overloaded': current_weight > max_weight,
            'free_weight_kg': round(max_weight - current_weight, 2),
        }

    async def add_xp(self, character_id: int, amount: int, admin_telegram_id: int | None = None, note: str | None = None) -> None:
        async with self.connect() as db:
            await db.execute('UPDATE characters SET xp = MAX(0, xp + ?) WHERE id = ?', (amount, character_id))
            await db.execute(
                """
                INSERT INTO transactions(character_id, admin_telegram_id, type, amount, note, created_at)
                VALUES (?, ?, 'xp', ?, ?, ?)
                """,
                (character_id, admin_telegram_id, amount, note, now_iso()),
            )
            details = f'Изменение XP: {amount:+d}.'
            if note:
                details += f'\nЗаметка: {note}'
            await self._add_journal_entry(db, character_id, 'xp', 'Изменение XP', details, admin_telegram_id)
            await db.commit()

    async def add_gold(self, character_id: int, amount: int, admin_telegram_id: int | None = None, note: str | None = None) -> None:
        async with self.connect() as db:
            await db.execute('UPDATE characters SET gold = MAX(0, gold + ?) WHERE id = ?', (amount, character_id))
            await db.execute(
                """
                INSERT INTO transactions(character_id, admin_telegram_id, type, amount, note, created_at)
                VALUES (?, ?, 'gold', ?, ?, ?)
                """,
                (character_id, admin_telegram_id, amount, note, now_iso()),
            )
            details = f'Изменение монет: {amount:+d} 🪙.'
            if note:
                details += f'\nЗаметка: {note}'
            await self._add_journal_entry(db, character_id, 'gold', 'Изменение монет', details, admin_telegram_id)
            await db.commit()

    async def grant_session_reward(
        self,
        session_id: int,
        xp_each: int,
        gold_each: int,
        admin_telegram_id: int | None = None,
        note: str | None = None,
    ) -> tuple[bool, str]:
        xp_each = max(0, int(xp_each))
        gold_each = max(0, int(gold_each))
        if xp_each == 0 and gold_each == 0:
            return False, 'В награде нет XP или монет.'

        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            session_cursor = await db.execute('SELECT title FROM game_sessions WHERE id = ?', (session_id,))
            session = await session_cursor.fetchone()
            if session is None:
                return False, 'Сессия не найдена.'

            characters_cursor = await db.execute(
                'SELECT id, display_name FROM characters WHERE session_id = ? ORDER BY display_name COLLATE NOCASE ASC',
                (session_id,),
            )
            characters = await characters_cursor.fetchall()
            if not characters:
                return False, 'В этой сессии нет персонажей.'

            for character in characters:
                character_id = int(character['id'])
                if xp_each:
                    await db.execute('UPDATE characters SET xp = xp + ? WHERE id = ?', (xp_each, character_id))
                    await db.execute(
                        """
                        INSERT INTO transactions(character_id, admin_telegram_id, type, amount, note, created_at)
                        VALUES (?, ?, 'quick_reward_xp', ?, ?, ?)
                        """,
                        (character_id, admin_telegram_id, xp_each, note, now_iso()),
                    )
                if gold_each:
                    await db.execute('UPDATE characters SET gold = gold + ? WHERE id = ?', (gold_each, character_id))
                    await db.execute(
                        """
                        INSERT INTO transactions(character_id, admin_telegram_id, type, amount, note, created_at)
                        VALUES (?, ?, 'quick_reward_gold', ?, ?, ?)
                        """,
                        (character_id, admin_telegram_id, gold_each, note, now_iso()),
                    )
                details = []
                if xp_each:
                    details.append(f'+{xp_each} XP')
                if gold_each:
                    details.append(f'+{gold_each} 🪙')
                if note:
                    details.append(str(note))
                await self._add_journal_entry(
                    db,
                    character_id,
                    'quick_reward',
                    'Быстрая награда',
                    '. '.join(details),
                    admin_telegram_id,
                )
            await db.commit()

            names = ', '.join(character['display_name'] for character in characters)
            parts = []
            if xp_each:
                parts.append(f'{xp_each} XP каждому')
            if gold_each:
                parts.append(f'{gold_each} 🪙 каждому')
            return True, (
                f'Быстрая награда выдана для сессии «{session["title"]}»: {", ".join(parts)}.\n'
                f'Получатели: {names}'
            )

    async def create_item(
        self,
        name: str,
        description: str,
        price: int,
        rarity: str,
        category: str = 'other',
        image_file_id: str | None = None,
        is_active: bool = True,
        shop_quantity: int = UNLIMITED_STOCK,
        loot_chance_percent: int = 0,
        weight_kg: float = 0,
        is_consumable: bool | None = None,
        equipment_slot: str | None = None,
        heal_hp: int = 0,
    ) -> int:
        clean_name = name.strip()
        clean_description = description.strip()
        clean_category = (category or 'other').strip()
        clean_price = max(0, int(price))
        sell_price = default_sell_price(clean_price)
        consumable_value = (
            infer_is_consumable(clean_name, clean_description, clean_category)
            if is_consumable is None else bool(is_consumable)
        )
        slot_value = (
            infer_equipment_slot(clean_name, clean_description, clean_category)
            if equipment_slot is None else str(equipment_slot).strip()
        )
        carry_bonus_kg = infer_carry_bonus_kg(clean_name, clean_description, clean_category)
        speed_penalty = infer_speed_penalty(clean_name, clean_description, clean_category)
        async with self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO shop_items(
                    name, description, price, sell_price, rarity, category, image_file_id,
                    is_active, shop_quantity, loot_chance_percent,
                    weight_kg, is_consumable, equipment_slot, carry_bonus_kg,
                    speed_penalty, heal_hp, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_name,
                    clean_description,
                    clean_price,
                    sell_price,
                    rarity.strip(),
                    clean_category,
                    image_file_id,
                    1 if is_active else 0,
                    max(UNLIMITED_STOCK, shop_quantity),
                    min(100, max(0, loot_chance_percent)),
                    max(0.0, float(weight_kg)),
                    1 if consumable_value else 0,
                    slot_value,
                    carry_bonus_kg,
                    speed_penalty,
                    max(0, int(heal_hp)),
                    now_iso(),
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def update_item_active(self, item_id: int, is_active: bool) -> None:
        async with self.connect() as db:
            await db.execute('UPDATE shop_items SET is_active = ? WHERE id = ?', (1 if is_active else 0, item_id))
            await db.commit()

    async def update_item_stock(self, item_id: int, shop_quantity: int) -> None:
        async with self.connect() as db:
            await db.execute('UPDATE shop_items SET shop_quantity = ? WHERE id = ?', (max(UNLIMITED_STOCK, shop_quantity), item_id))
            await db.commit()

    async def update_item_loot_chance(self, item_id: int, chance_percent: int) -> None:
        async with self.connect() as db:
            await db.execute(
                'UPDATE shop_items SET loot_chance_percent = ? WHERE id = ?',
                (min(100, max(0, chance_percent)), item_id),
            )
            await db.commit()

    async def update_item_consumable(self, item_id: int, is_consumable: bool) -> None:
        async with self.connect() as db:
            await db.execute('UPDATE shop_items SET is_consumable = ? WHERE id = ?', (1 if is_consumable else 0, item_id))
            await db.commit()

    async def update_item_equipment_slot(self, item_id: int, equipment_slot: str) -> None:
        clean_slot = str(equipment_slot or '').strip()
        async with self.connect() as db:
            await db.execute('UPDATE shop_items SET equipment_slot = ? WHERE id = ?', (clean_slot, item_id))
            if not clean_slot:
                await db.execute('DELETE FROM character_equipment WHERE item_id = ?', (item_id,))
            await db.commit()

    async def update_item_field(self, item_id: int, field: str, value: Any) -> None:
        allowed_fields = {
            'name',
            'description',
            'price',
            'sell_price',
            'rarity',
            'category',
            'image_file_id',
            'weight_kg',
            'carry_bonus_kg',
            'speed_penalty',
            'heal_hp',
        }
        if field not in allowed_fields:
            raise ValueError(f'Cannot edit item field: {field}')
        if field in {'price', 'sell_price', 'heal_hp'}:
            value = max(0, int(value))
        elif field in {'weight_kg', 'carry_bonus_kg'}:
            value = max(0.0, float(str(value).replace(',', '.')))
        elif field == 'speed_penalty':
            value = max(0, int(value))
        elif field == 'category':
            value = (str(value).strip() or 'other')
        elif field in {'name', 'description', 'rarity'}:
            value = str(value).strip()
        async with self.connect() as db:
            if field == 'price':
                await db.execute(
                    'UPDATE shop_items SET price = ?, sell_price = ? WHERE id = ?',
                    (value, default_sell_price(value), item_id),
                )
            else:
                await db.execute(f'UPDATE shop_items SET {field} = ? WHERE id = ?', (value, item_id))
            await db.commit()

    async def delete_item(self, item_id: int) -> None:
        async with self.connect() as db:
            await db.execute('DELETE FROM shop_items WHERE id = ?', (item_id,))
            await db.commit()

    async def list_item_categories(self, only_active: bool = True, only_purchasable: bool = False) -> list[str]:
        categories = await self.list_categories(
            only_with_items=True,
            only_active=only_active,
            only_purchasable=only_purchasable,
        )
        return [category['value'] for category in categories]

    async def list_loot_items(self) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT si.*, COALESCE(ic.title, si.category, '📦 Другое') AS category_title
                FROM shop_items si
                LEFT JOIN item_categories ic ON ic.value = COALESCE(si.category, 'other')
                WHERE si.loot_chance_percent > 0
                ORDER BY COALESCE(ic.sort_order, 999) ASC, COALESCE(ic.title, si.category) COLLATE NOCASE ASC, si.loot_chance_percent DESC, si.name COLLATE NOCASE ASC
                """
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def list_items(
        self,
        only_active: bool = True,
        category: str | None = None,
        only_purchasable: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT si.*, COALESCE(ic.title, si.category, '📦 Другое') AS category_title
            FROM shop_items si
            LEFT JOIN item_categories ic ON ic.value = COALESCE(si.category, 'other')
        """
        conditions: list[str] = []
        params: list[Any] = []
        if only_active or only_purchasable:
            conditions.append('si.is_active = 1')
        if only_purchasable:
            conditions.append('si.shop_quantity != 0')
        if category and category != 'all':
            conditions.append("COALESCE(si.category, 'other') = ?")
            params.append(category)
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY ic.sort_order ASC, COALESCE(ic.title, si.category) COLLATE NOCASE ASC, si.name COLLATE NOCASE ASC'
        if limit is not None:
            query += ' LIMIT ? OFFSET ?'
            params.extend([max(1, int(limit)), max(0, int(offset))])
        async with self.connect() as db:
            cursor = await db.execute(query, tuple(params))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_item(self, item_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT si.*, COALESCE(ic.title, si.category, '📦 Другое') AS category_title
                FROM shop_items si
                LEFT JOIN item_categories ic ON ic.value = COALESCE(si.category, 'other')
                WHERE si.id = ?
                """,
                (item_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def add_item_to_inventory(
        self,
        character_id: int,
        item_id: int,
        quantity: int,
        admin_telegram_id: int | None = None,
        note: str | None = None,
    ) -> None:
        if quantity == 0:
            return
        async with self.connect() as db:
            item_cursor = await db.execute('SELECT name FROM shop_items WHERE id = ?', (item_id,))
            item = await item_cursor.fetchone()
            await db.execute(
                """
                INSERT INTO inventory(character_id, item_id, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(character_id, item_id)
                DO UPDATE SET quantity = MAX(0, inventory.quantity + excluded.quantity)
                """,
                (character_id, item_id, quantity),
            )
            await db.execute('DELETE FROM inventory WHERE quantity <= 0')
            await self._cleanup_equipment_without_inventory(db)
            await db.execute(
                """
                INSERT INTO transactions(character_id, admin_telegram_id, type, amount, item_id, note, created_at)
                VALUES (?, ?, 'item', ?, ?, ?, ?)
                """,
                (character_id, admin_telegram_id, quantity, item_id, note, now_iso()),
            )
            item_name = item['name'] if item else 'предмет'
            action = 'получено' if quantity > 0 else 'убрано'
            details = f'{action.capitalize()}: {item_name} ×{abs(quantity)}.'
            if note:
                details += f'\nЗаметка: {note}'
            await self._add_journal_entry(db, character_id, 'item', 'Инвентарь изменён', details, admin_telegram_id)
            await db.commit()

    async def list_inventory(self, character_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT i.quantity,
                       CASE WHEN ce.item_id IS NULL THEN 0 ELSE 1 END AS is_equipped,
                       si.*,
                       COALESCE(ic.title, si.category, '📦 Другое') AS category_title
                FROM inventory i
                JOIN shop_items si ON si.id = i.item_id
                LEFT JOIN item_categories ic ON ic.value = COALESCE(si.category, 'other')
                LEFT JOIN character_equipment ce ON ce.character_id = i.character_id AND ce.item_id = i.item_id
                WHERE i.character_id = ? AND i.quantity > 0
                ORDER BY COALESCE(ic.sort_order, 999) ASC, COALESCE(ic.title, si.category) COLLATE NOCASE ASC, si.name COLLATE NOCASE ASC
                """,
                (character_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def _cleanup_equipment_without_inventory(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            DELETE FROM character_equipment
            WHERE NOT EXISTS (
                SELECT 1
                FROM inventory i
                WHERE i.character_id = character_equipment.character_id
                  AND i.item_id = character_equipment.item_id
                  AND i.quantity > 0
            )
            """
        )

    async def list_equipment(self, character_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT ce.slot, ce.equipped_at, si.*, COALESCE(ic.title, si.category, '📦 Другое') AS category_title
                FROM character_equipment ce
                JOIN shop_items si ON si.id = ce.item_id
                LEFT JOIN item_categories ic ON ic.value = COALESCE(si.category, 'other')
                JOIN inventory i ON i.character_id = ce.character_id AND i.item_id = ce.item_id AND i.quantity > 0
                WHERE ce.character_id = ?
                ORDER BY ce.slot COLLATE NOCASE ASC, si.name COLLATE NOCASE ASC
                """,
                (character_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def equip_item(self, character_id: int, item_id: int) -> tuple[bool, str]:
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            cursor = await db.execute(
                """
                SELECT i.quantity, si.name, COALESCE(si.equipment_slot, '') AS equipment_slot
                FROM inventory i
                JOIN shop_items si ON si.id = i.item_id
                WHERE i.character_id = ? AND i.item_id = ? AND i.quantity > 0
                """,
                (character_id, item_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return False, 'Такого предмета нет в инвентаре.'
            slot = str(row['equipment_slot'] or '').strip()
            if not slot:
                return False, 'Этот предмет нельзя экипировать.'
            await db.execute('DELETE FROM character_equipment WHERE character_id = ? AND item_id = ?', (character_id, item_id))
            await db.execute(
                """
                INSERT INTO character_equipment(character_id, slot, item_id, equipped_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(character_id, slot)
                DO UPDATE SET item_id = excluded.item_id, equipped_at = excluded.equipped_at
                """,
                (character_id, slot, item_id, now_iso()),
            )
            await db.execute(
                """
                INSERT INTO transactions(character_id, type, item_id, note, created_at)
                VALUES (?, 'equip_item', ?, ?, ?)
                """,
                (character_id, item_id, f'Equipped in slot {slot}', now_iso()),
            )
            await self._add_journal_entry(db, character_id, 'equip_item', 'Предмет экипирован', f'Экипировано: {row["name"]}.')
            await db.commit()
            return True, f'Экипировано: {row["name"]}.'

    async def unequip_item(self, character_id: int, item_id: int) -> tuple[bool, str]:
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            item_cursor = await db.execute('SELECT name FROM shop_items WHERE id = ?', (item_id,))
            item = await item_cursor.fetchone()
            cursor = await db.execute(
                'DELETE FROM character_equipment WHERE character_id = ? AND item_id = ?',
                (character_id, item_id),
            )
            if int(cursor.rowcount or 0) <= 0:
                await db.commit()
                return False, 'Этот предмет сейчас не экипирован.'
            name = item['name'] if item else 'предмет'
            await self._add_journal_entry(db, character_id, 'unequip_item', 'Предмет снят', f'Снято: {name}.')
            await db.commit()
            return True, f'Снято: {name}.'

    async def use_item(self, character_id: int, item_id: int) -> tuple[bool, str]:
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            cursor = await db.execute(
                """
                SELECT i.quantity, si.name, si.description,
                       COALESCE(si.is_consumable, 0) AS is_consumable,
                       COALESCE(si.heal_hp, 0) AS heal_hp,
                       COALESCE(c.hp, 0) AS hp,
                       COALESCE(c.max_hp, 1) AS max_hp
                FROM inventory i
                JOIN shop_items si ON si.id = i.item_id
                JOIN characters c ON c.id = i.character_id
                WHERE i.character_id = ? AND i.item_id = ? AND i.quantity > 0
                """,
                (character_id, item_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return False, 'Такого предмета нет в инвентаре.'
            if not int(row['is_consumable']):
                return False, 'Этот предмет не отмечен как расходуемый.'
            heal_hp = max(0, int(row['heal_hp'] or 0))
            before_hp = max(0, int(row['hp'] or 0))
            max_hp = max(1, int(row['max_hp'] or 1))
            if heal_hp > 0 and before_hp >= max_hp:
                return False, 'Сейчас этот предмет использовать нельзя.'

            update_cursor = await db.execute(
                'UPDATE inventory SET quantity = quantity - 1 WHERE character_id = ? AND item_id = ? AND quantity >= 1',
                (character_id, item_id),
            )
            if int(update_cursor.rowcount or 0) <= 0:
                return False, 'Предмет уже был использован другим действием.'
            await db.execute('DELETE FROM inventory WHERE quantity <= 0')
            await self._cleanup_equipment_without_inventory(db)
            restored_hp = 0
            if heal_hp > 0:
                after_hp = min(max_hp, before_hp + heal_hp)
                restored_hp = after_hp - before_hp
                await db.execute('UPDATE characters SET hp = ? WHERE id = ?', (after_hp, character_id))
            await db.execute(
                """
                INSERT INTO transactions(character_id, type, amount, item_id, note, created_at)
                VALUES (?, 'use_item', 1, ?, ?, ?)
                """,
                (character_id, item_id, 'Used from inventory', now_iso()),
            )
            await self._add_journal_entry(
                db,
                character_id,
                'use_item',
                'Предмет использован',
                f'Использовано: {row["name"]} ×1.',
            )
            await db.commit()

            description = str(row['description'] or '').strip()
            effect = f'\n\nЭффект/описание:\n{description}' if description else ''
            return True, f'Использовано: {row["name"]} ×1.{effect}'

    async def buy_item(self, character_id: int, item_id: int, quantity: int = 1) -> tuple[bool, str]:
        if quantity <= 0:
            return False, 'Количество должно быть больше 0.'

        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            item_cursor = await db.execute('SELECT * FROM shop_items WHERE id = ? AND is_active = 1', (item_id,))
            item = await item_cursor.fetchone()
            if item is None:
                return False, 'Предмет не найден или скрыт из магазина.'

            shop_quantity = int(item['shop_quantity'])
            if shop_quantity == 0:
                return False, 'Этот предмет закончился в магазине.'
            if shop_quantity > 0 and shop_quantity < quantity:
                return False, f'В магазине осталось только {shop_quantity} шт.'

            character_cursor = await db.execute('SELECT gold FROM characters WHERE id = ?', (character_id,))
            character = await character_cursor.fetchone()
            if character is None:
                return False, 'Персонаж не найден.'

            total_price = int(item['price']) * quantity
            if int(character['gold']) < total_price:
                return False, f'Не хватает монет. Нужно {total_price}, у тебя {character["gold"]}.'

            balance_cursor = await db.execute(
                'UPDATE characters SET gold = gold - ? WHERE id = ? AND gold >= ?',
                (total_price, character_id, total_price),
            )
            if int(balance_cursor.rowcount or 0) <= 0:
                return False, 'Баланс уже изменился. Обнови магазин и попробуй снова.'
            if shop_quantity > 0:
                stock_cursor = await db.execute(
                    'UPDATE shop_items SET shop_quantity = shop_quantity - ? WHERE id = ? AND shop_quantity >= ?',
                    (quantity, item_id, quantity),
                )
                if int(stock_cursor.rowcount or 0) <= 0:
                    return False, 'Остаток уже изменился. Обнови магазин и попробуй снова.'
            await db.execute(
                """
                INSERT INTO inventory(character_id, item_id, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(character_id, item_id)
                DO UPDATE SET quantity = inventory.quantity + excluded.quantity
                """,
                (character_id, item_id, quantity),
            )
            await db.execute(
                """
                INSERT INTO transactions(character_id, type, amount, item_id, note, created_at)
                VALUES (?, 'buy', ?, ?, ?, ?)
                """,
                (character_id, quantity, item_id, f'Bought for {total_price} gold', now_iso()),
            )
            await self._add_journal_entry(
                db,
                character_id,
                'buy',
                'Покупка в магазине',
                f'Куплено: {item["name"]} ×{quantity}. Потрачено {total_price} 🪙.',
            )
            await db.commit()
            return True, f'Покупка успешна: {item["name"]} ×{quantity}. Списано {total_price} монет.'

    async def sell_item(self, character_id: int, item_id: int, quantity: int = 1) -> tuple[bool, str]:
        if quantity <= 0:
            return False, 'Количество должно быть больше 0.'

        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            cursor = await db.execute(
                """
                SELECT i.quantity, si.name, si.price, COALESCE(si.sell_price, 0) AS sell_price
                FROM inventory i
                JOIN shop_items si ON si.id = i.item_id
                WHERE i.character_id = ? AND i.item_id = ?
                """,
                (character_id, item_id),
            )
            row = await cursor.fetchone()
            if row is None or int(row['quantity']) <= 0:
                return False, 'Такого предмета нет в инвентаре.'
            if int(row['quantity']) < quantity:
                return False, f'У тебя есть только {row["quantity"]} шт.'

            unit_sell_price = int(row['sell_price'] or 0)
            if unit_sell_price <= 0:
                unit_sell_price = default_sell_price(int(row['price'] or 0))
            total_price = unit_sell_price * quantity
            inventory_cursor = await db.execute(
                'UPDATE inventory SET quantity = quantity - ? WHERE character_id = ? AND item_id = ? AND quantity >= ?',
                (quantity, character_id, item_id, quantity),
            )
            if int(inventory_cursor.rowcount or 0) <= 0:
                return False, 'Количество предметов уже изменилось. Обнови инвентарь и попробуй снова.'
            await db.execute('DELETE FROM inventory WHERE quantity <= 0')
            await self._cleanup_equipment_without_inventory(db)
            await db.execute('UPDATE characters SET gold = gold + ? WHERE id = ?', (total_price, character_id))
            await db.execute(
                """
                INSERT INTO transactions(character_id, type, amount, item_id, note, created_at)
                VALUES (?, 'sell', ?, ?, ?, ?)
                """,
                (character_id, quantity, item_id, f'Sold for {total_price} gold', now_iso()),
            )
            await self._add_journal_entry(
                db,
                character_id,
                'sell',
                'Продажа предмета',
                f'Продано: {row["name"]} ×{quantity}. Получено {total_price} 🪙.',
            )
            await db.commit()
            return True, f'Продано: {row["name"]} ×{quantity}. Получено {total_price} монет.'

    async def transfer_gold(self, sender_id: int, recipient_id: int, amount: int) -> tuple[bool, str]:
        if amount <= 0:
            return False, 'Количество монет должно быть больше 0.'
        if sender_id == recipient_id:
            return False, 'Нельзя передать монеты самому себе.'

        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            sender_cursor = await db.execute('SELECT * FROM characters WHERE id = ?', (sender_id,))
            sender = await sender_cursor.fetchone()
            recipient_cursor = await db.execute('SELECT * FROM characters WHERE id = ?', (recipient_id,))
            recipient = await recipient_cursor.fetchone()
            if sender is None or recipient is None:
                return False, 'Персонаж не найден.'
            if sender['session_id'] != recipient['session_id']:
                return False, 'Нельзя передавать монеты персонажу из другой сессии.'
            if int(sender['gold']) < amount:
                return False, f'Не хватает монет. У тебя {sender["gold"]} 🪙.'

            sender_update = await db.execute(
                'UPDATE characters SET gold = gold - ? WHERE id = ? AND gold >= ?',
                (amount, sender_id, amount),
            )
            if int(sender_update.rowcount or 0) <= 0:
                return False, 'Баланс уже изменился. Обнови профиль и попробуй снова.'
            await db.execute('UPDATE characters SET gold = gold + ? WHERE id = ?', (amount, recipient_id))
            await db.execute(
                """
                INSERT INTO transactions(character_id, type, amount, note, created_at)
                VALUES (?, 'transfer_gold_out', ?, ?, ?)
                """,
                (sender_id, amount, f'To character #{recipient_id}', now_iso()),
            )
            await db.execute(
                """
                INSERT INTO transactions(character_id, type, amount, note, created_at)
                VALUES (?, 'transfer_gold_in', ?, ?, ?)
                """,
                (recipient_id, amount, f'From character #{sender_id}', now_iso()),
            )
            await self._add_journal_entry(
                db,
                sender_id,
                'transfer_gold_out',
                'Передача монет',
                f'Передано {amount} 🪙 персонажу {recipient["display_name"]}.',
            )
            await self._add_journal_entry(
                db,
                recipient_id,
                'transfer_gold_in',
                'Получены монеты',
                f'Получено {amount} 🪙 от персонажа {sender["display_name"]}.',
            )
            await db.commit()
            return True, f'Передано {amount} 🪙 персонажу {recipient["display_name"]}.'

    async def transfer_item(self, sender_id: int, recipient_id: int, item_id: int, quantity: int) -> tuple[bool, str]:
        if quantity <= 0:
            return False, 'Количество предметов должно быть больше 0.'
        if sender_id == recipient_id:
            return False, 'Нельзя передать предмет самому себе.'

        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            sender_item_cursor = await db.execute(
                """
                SELECT i.quantity, si.name
                FROM inventory i
                JOIN shop_items si ON si.id = i.item_id
                WHERE i.character_id = ? AND i.item_id = ?
                """,
                (sender_id, item_id),
            )
            sender_item = await sender_item_cursor.fetchone()
            if sender_item is None or int(sender_item['quantity']) <= 0:
                return False, 'Такого предмета нет в инвентаре.'
            if int(sender_item['quantity']) < quantity:
                return False, f'У тебя есть только {sender_item["quantity"]} шт.'

            recipient_cursor = await db.execute('SELECT * FROM characters WHERE id = ?', (recipient_id,))
            recipient = await recipient_cursor.fetchone()
            if recipient is None:
                return False, 'Получатель не найден.'
            sender_cursor = await db.execute('SELECT * FROM characters WHERE id = ?', (sender_id,))
            sender = await sender_cursor.fetchone()
            if sender is None:
                return False, 'Отправитель не найден.'
            if sender['session_id'] != recipient['session_id']:
                return False, 'Нельзя передавать предметы персонажу из другой сессии.'

            sender_update = await db.execute(
                'UPDATE inventory SET quantity = quantity - ? WHERE character_id = ? AND item_id = ? AND quantity >= ?',
                (quantity, sender_id, item_id, quantity),
            )
            if int(sender_update.rowcount or 0) <= 0:
                return False, 'Количество предметов уже изменилось. Обнови инвентарь и попробуй снова.'
            await db.execute('DELETE FROM inventory WHERE quantity <= 0')
            await self._cleanup_equipment_without_inventory(db)
            await db.execute(
                """
                INSERT INTO inventory(character_id, item_id, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(character_id, item_id)
                DO UPDATE SET quantity = inventory.quantity + excluded.quantity
                """,
                (recipient_id, item_id, quantity),
            )
            await db.execute(
                """
                INSERT INTO transactions(character_id, type, amount, item_id, note, created_at)
                VALUES (?, 'transfer_item_out', ?, ?, ?, ?)
                """,
                (sender_id, quantity, item_id, f'To character #{recipient_id}', now_iso()),
            )
            await db.execute(
                """
                INSERT INTO transactions(character_id, type, amount, item_id, note, created_at)
                VALUES (?, 'transfer_item_in', ?, ?, ?, ?)
                """,
                (recipient_id, quantity, item_id, f'From character #{sender_id}', now_iso()),
            )
            await self._add_journal_entry(
                db,
                sender_id,
                'transfer_item_out',
                'Передача предмета',
                f'Передано: {sender_item["name"]} ×{quantity} персонажу {recipient["display_name"]}.',
            )
            await self._add_journal_entry(
                db,
                recipient_id,
                'transfer_item_in',
                'Получен предмет',
                f'Получено: {sender_item["name"]} ×{quantity} от персонажа {sender["display_name"]}.',
            )
            await db.commit()
            return True, f'Передано: {sender_item["name"]} ×{quantity} персонажу {recipient["display_name"]}.'

    async def create_quest(
        self,
        title: str,
        description: str,
        xp_reward: int,
        gold_reward: int,
        item_id: int | None = None,
        item_quantity: int = 0,
    ) -> int:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO quests(title, description, xp_reward, gold_reward, item_id, item_quantity, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title.strip(),
                    description.strip(),
                    max(0, xp_reward),
                    max(0, gold_reward),
                    item_id,
                    max(0, item_quantity),
                    now_iso(),
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def list_quests(self, only_active: bool = True) -> list[dict[str, Any]]:
        query = """
            SELECT q.*, si.name AS item_name
            FROM quests q
            LEFT JOIN shop_items si ON si.id = q.item_id
        """
        if only_active:
            query += ' WHERE q.is_active = 1'
        query += ' ORDER BY q.created_at DESC, q.title COLLATE NOCASE ASC'
        async with self.connect() as db:
            cursor = await db.execute(query)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_quest(self, quest_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT q.*, si.name AS item_name
                FROM quests q
                LEFT JOIN shop_items si ON si.id = q.item_id
                WHERE q.id = ?
                """,
                (quest_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_quest_active(self, quest_id: int, is_active: bool) -> None:
        async with self.connect() as db:
            await db.execute('UPDATE quests SET is_active = ? WHERE id = ?', (1 if is_active else 0, quest_id))
            await db.commit()

    async def award_quest(self, quest_id: int, character_ids: list[int], admin_telegram_id: int | None = None) -> tuple[bool, str]:
        character_ids = list(dict.fromkeys(character_ids))
        if not character_ids:
            return False, 'Нужно выбрать хотя бы одного персонажа.'

        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            quest_cursor = await db.execute('SELECT * FROM quests WHERE id = ?', (quest_id,))
            quest = await quest_cursor.fetchone()
            if quest is None:
                return False, 'Квест не найден.'

            characters_cursor = await db.execute(
                f'SELECT * FROM characters WHERE id IN ({",".join("?" for _ in character_ids)})',
                tuple(character_ids),
            )
            characters = await characters_cursor.fetchall()
            if not characters:
                return False, 'Выбранные персонажи не найдены.'

            placeholders = ','.join('?' for _ in character_ids)
            awards_cursor = await db.execute(
                f'SELECT character_id FROM quest_awards WHERE quest_id = ? AND character_id IN ({placeholders})',
                (quest_id, *character_ids),
            )
            already_awarded = {int(row['character_id']) for row in await awards_cursor.fetchall()}
            characters = [character for character in characters if int(character['id']) not in already_awarded]
            if not characters:
                return False, 'Эти персонажи уже получали награду за данный квест.'

            count = len(characters)
            xp_each = (int(quest['xp_reward']) + count - 1) // count if int(quest['xp_reward']) > 0 else 0
            gold_each = (int(quest['gold_reward']) + count - 1) // count if int(quest['gold_reward']) > 0 else 0
            item_each = (int(quest['item_quantity']) + count - 1) // count if quest['item_id'] and int(quest['item_quantity']) > 0 else 0

            for character in characters:
                character_id = int(character['id'])
                if xp_each:
                    await db.execute('UPDATE characters SET xp = xp + ? WHERE id = ?', (xp_each, character_id))
                    await db.execute(
                        """
                        INSERT INTO transactions(character_id, admin_telegram_id, type, amount, note, created_at)
                        VALUES (?, ?, 'quest_xp', ?, ?, ?)
                        """,
                        (character_id, admin_telegram_id, xp_each, f'Quest #{quest_id}: {quest["title"]}', now_iso()),
                    )
                if gold_each:
                    await db.execute('UPDATE characters SET gold = gold + ? WHERE id = ?', (gold_each, character_id))
                    await db.execute(
                        """
                        INSERT INTO transactions(character_id, admin_telegram_id, type, amount, note, created_at)
                        VALUES (?, ?, 'quest_gold', ?, ?, ?)
                        """,
                        (character_id, admin_telegram_id, gold_each, f'Quest #{quest_id}: {quest["title"]}', now_iso()),
                    )
                if item_each:
                    await db.execute(
                        """
                        INSERT INTO inventory(character_id, item_id, quantity)
                        VALUES (?, ?, ?)
                        ON CONFLICT(character_id, item_id)
                        DO UPDATE SET quantity = inventory.quantity + excluded.quantity
                        """,
                        (character_id, int(quest['item_id']), item_each),
                    )
                    await db.execute(
                        """
                        INSERT INTO transactions(character_id, admin_telegram_id, type, amount, item_id, note, created_at)
                        VALUES (?, ?, 'quest_item', ?, ?, ?, ?)
                        """,
                        (character_id, admin_telegram_id, item_each, int(quest['item_id']), f'Quest #{quest_id}: {quest["title"]}', now_iso()),
                    )
                details = []
                if xp_each:
                    details.append(f'+{xp_each} XP')
                if gold_each:
                    details.append(f'+{gold_each} 🪙')
                if item_each:
                    details.append(f'предмет #{int(quest["item_id"])} ×{item_each}')
                await self._add_journal_entry(
                    db,
                    character_id,
                    'quest_reward',
                    f'Награда за квест: {quest["title"]}',
                    ', '.join(details) if details else 'Квест отмечен без материальной награды.',
                    admin_telegram_id,
                )
                await db.execute(
                    """
                    INSERT INTO quest_awards(quest_id, character_id, admin_telegram_id, awarded_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (quest_id, character_id, admin_telegram_id, now_iso()),
                )
            await db.commit()

            names = ', '.join(character['display_name'] for character in characters)
            parts = []
            if xp_each:
                parts.append(f'{xp_each} XP каждому')
            if gold_each:
                parts.append(f'{gold_each} 🪙 каждому')
            if item_each:
                parts.append(f'предмет ×{item_each} каждому')
            reward_text = ', '.join(parts) if parts else 'награда без XP/монет/предметов'
            return True, f'Награда за квест «{quest["title"]}» выдана: {reward_text}.\nПолучатели: {names}'

    async def roll_random_loot(self, character_id: int, admin_telegram_id: int | None = None) -> tuple[bool, str]:
        async with self.connect() as db:
            character_cursor = await db.execute('SELECT * FROM characters WHERE id = ?', (character_id,))
            character = await character_cursor.fetchone()
            if character is None:
                return False, 'Персонаж не найден.'

            loot_cursor = await db.execute(
                'SELECT * FROM shop_items WHERE loot_chance_percent > 0 ORDER BY loot_chance_percent DESC, name COLLATE NOCASE ASC'
            )
            loot_items = await loot_cursor.fetchall()
            if not loot_items:
                return False, 'Таблица рандомного лута пустая. Укажи шанс лута хотя бы у одного предмета.'

            won_items = []
            rolls = []
            for item in loot_items:
                chance = int(item['loot_chance_percent'])
                roll = random.randint(1, 100)
                rolls.append(f'{item["name"]}: {roll}/{chance}')
                if roll <= chance:
                    won_items.append(item)

            for item in won_items:
                await db.execute(
                    """
                    INSERT INTO inventory(character_id, item_id, quantity)
                    VALUES (?, ?, 1)
                    ON CONFLICT(character_id, item_id)
                    DO UPDATE SET quantity = inventory.quantity + 1
                    """,
                    (character_id, int(item['id'])),
                )
                await db.execute(
                    """
                    INSERT INTO transactions(character_id, admin_telegram_id, type, amount, item_id, note, created_at)
                    VALUES (?, ?, 'random_loot', 1, ?, ?, ?)
                    """,
                    (character_id, admin_telegram_id, int(item['id']), f'Random loot: {item["loot_chance_percent"]}%', now_iso()),
                )
                await self._add_journal_entry(
                    db,
                    character_id,
                    'random_loot',
                    'Рандомный лут',
                    f'Выпало: {item["name"]} ×1.',
                    admin_telegram_id,
                )
            await db.commit()

            if won_items:
                loot_text = '\n'.join(f'• {item["name"]} ×1 ({item["loot_chance_percent"]}%)' for item in won_items)
                return True, f'🎲 Рандомный лут для {character["display_name"]}:\n{loot_text}'
            return True, f'🎲 Рандомный лут для {character["display_name"]}: ничего не выпало.\n\nБроски:\n' + '\n'.join(rolls)
