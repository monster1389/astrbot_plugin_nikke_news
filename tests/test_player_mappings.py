import json
from datetime import datetime, timedelta, timezone

from message_builder import MessageBuilder
from player_mapping_cache import PlayerMappingCache
from player_mapping_refresher import (
    extract_character_map,
    extract_state_effect_options,
)


def test_extract_character_map_from_cdn_list():
    data = [
        {"name_code": 101, "name_localkey": {"name": "Anis"}},
        {"name_code": 102, "name_localkey": {"name": "Rapi"}},
    ]

    en_map, display_map = extract_character_map(data)
    assert en_map == {"Anis": 101, "Rapi": 102}
    assert display_map == {}


def test_extract_state_effect_options_from_equip_table():
    data = [
        {
            "state_effect_id_list": [9001, "9002"],
            "description_localkey": "ATK",
            "state_effect_group_id": 10,
        }
    ]

    result = extract_state_effect_options(data)

    assert result["9001"]["description"] == "ATK"
    assert result["9002"]["group_id"] == 10


def test_equipment_option_value_uses_frontend_percent_logic():
    msg = MessageBuilder.format_character_stats(
        {"combat": 123},
        {
            "skill1_lv": 1,
            "skill2_lv": 2,
            "burst_skill_lv": 3,
            "head_equip_option1_id": 9001,
        },
        {"en": "Anis"},
        [
            {
                "id": 9001,
                "function_details": [
                    {"function_type": "StatAtk", "function_value": 1234}
                ],
            }
        ],
        {"9001": {"description": "ATK", "group_id": 1}},
    )

    assert "ATK: 12.34%" in msg


def test_equipment_option_value_abs_and_aggregate_same_type():
    msg = MessageBuilder.format_character_stats(
        {"combat": 123},
        {
            "head_equip_option1_id": 9001,
            "arm_equip_option1_id": 9002,
        },
        {"en": "Anis"},
        [
            {
                "id": 9001,
                "function_details": [
                    {"function_type": "StatAtk", "function_value": -100}
                ],
            },
            {
                "id": 9002,
                "function_details": [
                    {"function_type": "StatAtk", "function_value": 250}
                ],
            },
        ],
        {
            "9001": {"description": "ATK", "group_id": 1},
            "9002": {"description": "ATK", "group_id": 1},
        },
    )

    assert "ATK: 3.50%" in msg


def test_mapping_cache_stale_and_language(tmp_path):
    path = tmp_path / "player_mappings.json"
    path.write_text(
        json.dumps(
            {
                "language": "en",
                "updated_at": (
                    datetime.now(timezone.utc) - timedelta(hours=200)
                ).isoformat(),
                "characters": {"Anis": 101},
                "state_effect_options": {"9001": {"description": "ATK"}},
            }
        ),
        encoding="utf-8",
    )

    cache = PlayerMappingCache(path)
    assert cache.load() is True
    assert cache.has_useful_data("en") is True
    assert cache.has_useful_data("ja") is False
    assert cache.is_stale(168) is True
