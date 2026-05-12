from unittest.mock import MagicMock

from core.config import PluginConfig
from player.character_service import CharacterService


def _make_service(**overrides) -> CharacterService:
    client = MagicMock()
    config = PluginConfig({"玩家": {"nikke查询": {}}})
    service = CharacterService(client, config)
    service._name_to_code = overrides.get("name_to_code", {"Anis": 101, "Rapi": 102})
    service._code_to_name = overrides.get("code_to_name", {})
    service._aliases = overrides.get("aliases", {})
    service._state_effect_options = {}
    return service


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
