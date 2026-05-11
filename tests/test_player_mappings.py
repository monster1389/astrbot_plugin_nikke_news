import json
from datetime import datetime, timedelta, timezone

from core.message_builder import MessageBuilder
from player.player_mapping_cache import PlayerMappingCache
from player.player_mapping_refresher import (
    extract_character_names,
    extract_state_effect_options,
)


def test_extract_character_names_from_localized_data():
    """Pre-localized CDN data: name_localkey uses {"name": "Anis"} single-key format."""
    data = [
        {"name_code": 101, "name_localkey": {"name": "Anis"}},
        {"name_code": 102, "name_localkey": {"name": "Rapi"}},
    ]

    result = extract_character_names(data)
    assert result == {101: "Anis", 102: "Rapi"}


def test_extract_character_names_with_string_localkey():
    data = [
        {"name_code": 101, "name_localkey": "Anis"},
        {"name_code": 102, "name_localkey": "Rapi"},
    ]

    result = extract_character_names(data)
    assert result == {101: "Anis", 102: "Rapi"}


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


def test_extract_state_effect_options_with_string_desc():
    """CDN returns plain string descriptions like \"【攻擊力增加】\"."""
    data = [
        {
            "state_effect_id_list": [9310101],
            "description_localkey": "【攻擊力增加】",
            "state_effect_group_id": 1,
        }
    ]

    result = extract_state_effect_options(data)
    assert result["9310101"]["description"] == "【攻擊力增加】"


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


def test_mapping_cache_name_to_code_reverses_character_names():
    cache = PlayerMappingCache(None)
    cache.save(
        language="en",
        character_names={101: "Anis", 102: "Rapi"},
        state_effect_options={"9001": {"description": "ATK"}},
    )

    assert cache.has_useful_data() is True
    assert cache.name_to_code() == {"Anis": 101, "Rapi": 102}


def test_mapping_cache_stale(tmp_path):
    path = tmp_path / "player_mappings_en.json"
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "language": "en",
                "updated_at": (
                    datetime.now(timezone.utc) - timedelta(hours=200)
                ).isoformat(),
                "character_names": {"101": "Anis"},
                "state_effect_options": {"9001": {"description": "ATK"}},
            }
        ),
        encoding="utf-8",
    )

    cache = PlayerMappingCache(path)
    assert cache.load() is True
    assert cache.has_useful_data() is True
    assert cache.is_stale(168) is True


def test_mapping_cache_empty_has_no_useful_data():
    cache = PlayerMappingCache(None)
    assert cache.has_useful_data() is False
    assert cache.name_to_code() == {}
