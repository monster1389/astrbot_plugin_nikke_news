"""技能服务测试。"""

import json
from datetime import datetime, timezone


from player.skill_service import SkillService, SkillError


SAMPLE_SKILL_DATA = {
    "resource_id": 511,
    "name_code": 5124,
    "name_localkey": "Cinderella",
    "updated_at": "2026-06-05T00:00:00+00:00",
    "skill1_detail": {
        "name_localkey": "Flawless Glass",
        "info_description_localkey": "Skill 1",
        "description_localkey": (
            "■ Activates when entering Burst Stage 3. Affects self.\n"
            "<color=#00AEFF>ATK ▲ {description_value_01}% of caster's "
            "<word_group=10025>final</word_group> Max HP "
            "for {description_value_02} sec.</color>"
        ),
        "description_value_list": [
            {
                "description_value": [
                    "1.7",
                    "1.8",
                    "1.92",
                    "2.02",
                    "2.13",
                    "2.26",
                    "2.36",
                    "2.49",
                    "2.58",
                    "2.71",
                ]
            },
            {
                "description_value": [
                    "10",
                    "10",
                    "10",
                    "10",
                    "10",
                    "10",
                    "10",
                    "10",
                    "10",
                    "10",
                ]
            },
            {},
        ],
    },
    "skill2_detail": {
        "name_localkey": "Dirt-Resistant Mirror",
        "info_description_localkey": "Skill 2",
        "description_localkey": "Decoy: {description_value_01}% HP.",
        "description_value_list": [
            {
                "description_value": [
                    "52.8",
                    "57.6",
                    "62.4",
                    "67.2",
                    "72",
                    "76.8",
                    "81.6",
                    "86.4",
                    "91.2",
                    "96",
                ]
            },
        ],
    },
    "ulti_skill_detail": {
        "name_localkey": "Glass Slippers",
        "info_description_localkey": "Burst Skill",
        "description_localkey": "Deals {description_value_01}% damage for {description_value_02} time(s).",
        "description_value_list": [
            {
                "description_value": [
                    "853.7",
                    "910.62",
                    "967.5",
                    "1024.46",
                    "1081.38",
                    "1138.26",
                    "1195.16",
                    "1252.08",
                    "1309",
                    "1365.92",
                ]
            },
            {
                "description_value": [
                    "10",
                    "10",
                    "10",
                    "10",
                    "10",
                    "10",
                    "10",
                    "10",
                    "10",
                    "10",
                ]
            },
        ],
    },
}


class TestFormatSkills:
    """测试 _format_skills 格式化输出。"""

    def test_format_all_skills_level_10(self):
        levels = {"skill1": 10, "skill2": 10, "burst": 10}
        result = SkillService._format_skills(SAMPLE_SKILL_DATA, levels, "Cinderella")
        assert "Cinderella" in result
        assert "Skill 1 — Flawless Glass" in result
        assert "Skill 2 — Dirt-Resistant Mirror" in result
        assert "Burst Skill — Glass Slippers" in result
        assert "2.71%" in result
        assert "for 10 sec" in result
        assert "96%" in result
        assert "1365.92%" in result

    def test_format_skill1_level_1(self):
        levels = {"skill1": 1, "skill2": 10, "burst": 10}
        result = SkillService._format_skills(SAMPLE_SKILL_DATA, levels, "Cinderella")
        assert "1.7%" in result
        assert "2.71%" not in result

    def test_strips_color_and_word_group_tags(self):
        levels = {"skill1": 10, "skill2": 10, "burst": 10}
        result = SkillService._format_skills(SAMPLE_SKILL_DATA, levels, "Cinderella")
        assert "<color=" not in result
        assert "</color>" not in result
        assert "<word_group=" not in result
        assert "</word_group>" not in result
        assert "final" in result  # word_group content preserved

    def test_handles_missing_level_defaults_to_1(self):
        levels = {}
        result = SkillService._format_skills(SAMPLE_SKILL_DATA, levels, "Cinderella")
        assert "1.7%" in result  # level 1 value

    def test_handles_out_of_range_level(self):
        levels = {"skill1": 99, "skill2": 10, "burst": 10}
        result = SkillService._format_skills(SAMPLE_SKILL_DATA, levels, "Cinderella")
        assert "2.71%" in result  # capped at max index


class TestSkillCachePath:
    """测试缓存路径生成。"""

    def test_cache_path_format(self, tmp_path):
        skills_dir = tmp_path / "skills"
        service = SkillService.__new__(SkillService)
        service._skills_dir = skills_dir
        path = service._cache_path(5124, "zh-TW")
        assert path == skills_dir / "5124_zh-TW.json"

    def test_ensure_skills_dir(self, tmp_path):
        skills_dir = tmp_path / "skills"
        service = SkillService.__new__(SkillService)
        service._skills_dir = skills_dir
        service._ensure_skills_dir()
        assert skills_dir.exists()


class TestSkillError:
    def test_is_exception(self):
        err = SkillError("test message")
        assert isinstance(err, Exception)
        assert str(err) == "test message"


class TestLoadCache:
    def test_loads_valid_cache(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        cache_path = skills_dir / "5124_zh-TW.json"
        data = dict(
            SAMPLE_SKILL_DATA, updated_at=datetime.now(timezone.utc).isoformat()
        )
        cache_path.write_text(json.dumps(data, ensure_ascii=False))

        service = SkillService.__new__(SkillService)
        service._skills_dir = skills_dir
        service._ttl_hours = 168
        result = service._load_cache(5124, "zh-TW")
        assert result is not None
        assert result["resource_id"] == 511

    def test_returns_none_for_missing_cache(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        service = SkillService.__new__(SkillService)
        service._skills_dir = skills_dir
        service._ttl_hours = 168
        assert service._load_cache(5124, "zh-TW") is None

    def test_returns_none_for_stale_cache(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        cache_path = skills_dir / "5124_zh-TW.json"
        stale_data = dict(SAMPLE_SKILL_DATA, updated_at="2020-01-01T00:00:00+00:00")
        cache_path.write_text(json.dumps(stale_data, ensure_ascii=False))

        service = SkillService.__new__(SkillService)
        service._skills_dir = skills_dir
        service._ttl_hours = 168
        assert service._load_cache(5124, "zh-TW") is None

    def test_returns_none_for_invalid_json(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        cache_path = skills_dir / "5124_zh-TW.json"
        cache_path.write_text("not valid json")

        service = SkillService.__new__(SkillService)
        service._skills_dir = skills_dir
        service._ttl_hours = 168
        assert service._load_cache(5124, "zh-TW") is None
