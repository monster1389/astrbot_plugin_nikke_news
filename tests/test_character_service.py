from unittest.mock import MagicMock

from core.config import PluginConfig
from player.character_service import CharacterService
from player.player_mapping_cache import PlayerMappingCache


def _make_service(**overrides) -> CharacterService:
    client = MagicMock()
    config = PluginConfig({"玩家": {"nikke查询": {}}})
    service = CharacterService(client, config)
    name_to_code = overrides.get("name_to_code", {"Anis": 101, "Rapi": 102})
    service._code_to_en_name = {code: name for name, code in name_to_code.items()}
    service._code_to_name = overrides.get("code_to_name", {})
    service._aliases = overrides.get("aliases", {})
    service._state_effect_options = {}
    return service


def _stale_cache() -> PlayerMappingCache:
    cache = PlayerMappingCache(None)
    cache._data = {
        "character_names": {"101": "Anis"},
        "state_effect_options": {"skill_1": {"id": "skill_1"}},
    }
    cache._updated_at = "2000-01-01T00:00:00+00:00"
    return cache


def _fresh_cache() -> PlayerMappingCache:
    cache = PlayerMappingCache(None)
    cache._data = {
        "character_names": {"101": "Anis"},
        "state_effect_options": {"skill_1": {"id": "skill_1"}},
    }
    cache._updated_at = "2099-12-31T23:59:59+00:00"
    return cache


class TestIsLoaded:
    def test_true(self):
        svc = _make_service(name_to_code={"Anis": 101})
        assert svc.is_loaded is True

    def test_false(self):
        svc = _make_service(name_to_code={})
        assert svc.is_loaded is False


class TestCount:
    def test_matches_dict_len(self):
        svc = _make_service(name_to_code={"Anis": 101, "Rapi": 102})
        assert svc.count() == 2

    def test_zero(self):
        svc = _make_service(name_to_code={})
        assert svc.count() == 0


class TestBuildAliasMap:
    def test_empty(self):
        svc = _make_service(aliases={})
        assert svc._build_alias_map() == {}

    def test_populated(self):
        svc = _make_service(aliases={"Anis": ["anis spark", "an1s"]})
        result = svc._build_alias_map()
        assert result == {"anis spark": "Anis", "an1s": "Anis"}

    def test_case_insensitive(self):
        svc = _make_service(aliases={"Anis": ["ANIS Spark"]})
        result = svc._build_alias_map()
        assert result["anis spark"] == "Anis"


class TestDisplayName:
    def test_found(self):
        svc = _make_service(code_to_name={101: "アニス"})
        assert svc._display_name(101, "Anis") == "アニス"

    def test_fallback(self):
        svc = _make_service(code_to_name={})
        assert svc._display_name(999, "Unknown") == "Unknown"


class TestLookup:
    def test_empty_query(self):
        svc = _make_service()
        assert svc.lookup("") == []
        assert svc.lookup("   ") == []

    def test_exact_alias_match(self):
        svc = _make_service(
            name_to_code={"Anis": 101},
            aliases={"Anis": ["ani spark"]},
        )
        result = svc.lookup("ani spark")
        assert result == [(101, "Anis")]

    def test_exact_en_match(self):
        svc = _make_service(name_to_code={"Anis": 101, "Rapi": 102})
        result = svc.lookup("Anis")
        assert result == [(101, "Anis")]

    def test_exact_en_case_insensitive(self):
        svc = _make_service(name_to_code={"Anis": 101})
        result = svc.lookup("anis")
        assert result == [(101, "Anis")]

    def test_exact_localized_match(self):
        svc = _make_service(
            name_to_code={"Anis": 101},
            code_to_name={101: "アニス"},
        )
        result = svc.lookup("アニス")
        assert result == [(101, "アニス")]

    def test_en_substring(self):
        svc = _make_service(name_to_code={"Anis": 101, "Rapi": 102})
        result = svc.lookup("ani")
        assert result == [(101, "Anis")]

    def test_localized_substring(self):
        svc = _make_service(
            name_to_code={"Alice": 201},
            code_to_name={201: "アリス"},
        )
        result = svc.lookup("アリ")
        assert result == [(201, "アリス")]

    def test_no_match(self):
        svc = _make_service(name_to_code={"Anis": 101})
        assert svc.lookup("unknown") == []

    def test_dedup_across_steps(self):
        svc = _make_service(
            name_to_code={"Anis": 101},
            code_to_name={101: "Anis"},
        )
        result = svc.lookup("anis")
        assert len(result) == 1
        assert result[0][0] == 101

    def test_duplicate_name_returns_all(self):
        svc = _make_service(name_to_code={"Anis": 101})
        svc._code_to_en_name = {101: "Sakura", 201: "Rei", 301: "Sakura"}
        result = svc.lookup("Sakura")
        assert len(result) == 2
        assert (101, "Sakura") in result
        assert (301, "Sakura") in result

    def test_duplicate_name_alias_returns_all(self):
        svc = _make_service(name_to_code={"Anis": 101})
        svc._code_to_en_name = {101: "Sakura", 301: "Sakura"}
        svc._aliases = {"Sakura": ["sak"]}
        result = svc.lookup("sak")
        assert len(result) == 2


class TestIsMappingStale:
    def test_en_cache_none(self):
        svc = _make_service()
        assert svc.is_mapping_stale() is True

    def test_en_cache_no_useful_data(self):
        svc = _make_service()
        cache = PlayerMappingCache(None)
        # _data is already {} from __init__, so has_useful_data() → False
        svc._en_cache = cache
        assert svc.is_mapping_stale() is True

    def test_en_cache_is_stale(self):
        svc = _make_service()
        svc._en_cache = _stale_cache()
        assert svc.is_mapping_stale() is True

    def test_en_cache_fresh_no_target(self):
        svc = _make_service()
        svc._en_cache = _fresh_cache()
        svc._target_cache = None
        assert svc.is_mapping_stale() is False

    def test_target_lang_is_en_skip_target_check(self):
        svc = _make_service()
        svc._en_cache = _fresh_cache()
        svc._target_cache = _stale_cache()
        svc._config = PluginConfig({"玩家": {"nikke查询": {"mapping_language": "en"}}})
        assert svc.is_mapping_stale() is False

    def test_target_cache_none_skip_target_check(self):
        svc = _make_service()
        svc._en_cache = _fresh_cache()
        svc._target_cache = None
        svc._config = PluginConfig(
            {"玩家": {"nikke查询": {"mapping_language": "zh-TW"}}}
        )
        assert svc.is_mapping_stale() is False

    def test_target_no_useful_data(self):
        svc = _make_service()
        svc._en_cache = _fresh_cache()
        target = PlayerMappingCache(None)
        # _data is already {} from __init__, so has_useful_data() → False
        svc._target_cache = target
        svc._config = PluginConfig(
            {"玩家": {"nikke查询": {"mapping_language": "zh-TW"}}}
        )
        assert svc.is_mapping_stale() is True

    def test_target_is_stale(self):
        svc = _make_service()
        svc._en_cache = _fresh_cache()
        svc._target_cache = _stale_cache()
        svc._config = PluginConfig(
            {"玩家": {"nikke查询": {"mapping_language": "zh-TW"}}}
        )
        assert svc.is_mapping_stale() is True

    def test_both_fresh(self):
        svc = _make_service()
        svc._en_cache = _fresh_cache()
        svc._target_cache = _fresh_cache()
        svc._config = PluginConfig(
            {"玩家": {"nikke查询": {"mapping_language": "zh-TW"}}}
        )
        assert svc.is_mapping_stale() is False
