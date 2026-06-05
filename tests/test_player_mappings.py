import json
from datetime import datetime, timedelta, timezone

from player.character_formatter import format_character_stats
from player.player_mapping_cache import PlayerMappingCache
from core.utils import accept_language
from player.player_mapping_refresher import (
    _localized_text,
    extract_character_names,
    extract_resource_ids,
    extract_state_effect_options,
    parse_cookie_header,
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
    msg = format_character_stats(
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
    msg = format_character_stats(
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


# ── _localized_text ──────────────────────────────────────────────


def test_localized_text_string():
    assert _localized_text("Anis") == "Anis"


def test_localized_text_dict_name():
    assert _localized_text({"name": "Anis"}) == "Anis"


def test_localized_text_dict_description():
    assert _localized_text({"description": "ATK"}) == "ATK"


def test_localized_text_dict_fallback_keys():
    assert _localized_text({"en": "Alice"}) == "Alice"
    assert _localized_text({"ja": "アリス"}) == "アリス"
    assert _localized_text({"zh-TW": "愛麗絲"}) == "愛麗絲"


def test_localized_text_empty():
    assert _localized_text("") == ""
    assert _localized_text(None) == ""
    assert _localized_text({}) == ""


# ── parse_cookie_header ─────────────────────────────────────────


def test_parse_cookie_header_single():
    result = parse_cookie_header("token=abc123")
    names = {c["name"] for c in result}
    domains = {c["domain"] for c in result}
    assert names == {"token"}
    assert ".blablalink.com" in domains
    assert "www.blablalink.com" in domains
    for c in result:
        assert c["value"] == "abc123"
        assert c["path"] == "/"
        assert c["secure"] is True


def test_parse_cookie_header_multiple():
    result = parse_cookie_header("a=1; b=2")
    assert len(result) == 4  # 2 names x 2 domains


def test_parse_cookie_header_empty():
    assert parse_cookie_header("") == []


# ── accept_language ─────────────────────────────────────────────


def test_accept_language_en():
    assert "en-US" in accept_language("en")


def test_accept_language_zh_tw():
    assert "zh-TW" in accept_language("zh-TW")


def test_accept_language_other():
    result = accept_language("ja")
    assert result.startswith("ja")
    assert "en" in result


# ── extract edge cases ───────────────────────────────────────────


def test_extract_character_names_non_list():
    assert extract_character_names({"not": "list"}) == {}


def test_extract_state_effect_options_records_format():
    data = {
        "records": [
            {
                "state_effect_id_list": [8001],
                "description_localkey": "ATK Boost",
                "state_effect_group_id": 5,
            }
        ]
    }
    result = extract_state_effect_options(data)
    assert result["8001"]["description"] == "ATK Boost"


def test_extract_state_effect_options_non_dict_items():
    data = [
        "not a dict",
        {
            "state_effect_id_list": [7001],
            "description_localkey": "DEF",
            "state_effect_group_id": 3,
        },
    ]
    result = extract_state_effect_options(data)
    assert result["7001"]["description"] == "DEF"
    assert len(result) == 1


def test_extract_resource_ids_from_character_list():
    data = [
        {"name_code": 5124, "resource_id": 511, "name_localkey": "Cinderella"},
        {"name_code": 1489, "resource_id": 470, "name_localkey": "Red Hood"},
        {"name_code": 9999, "name_localkey": "NoResource"},  # no resource_id
        "not_a_dict",
    ]

    result = extract_resource_ids(data)
    assert result == {5124: 511, 1489: 470}


def test_extract_resource_ids_empty():
    assert extract_resource_ids([]) == {}
    assert extract_resource_ids(None) == {}
    assert extract_resource_ids("not_a_list") == {}
