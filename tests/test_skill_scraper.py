"""技能抓取器测试。"""
import json

import pytest

from player.skill_scraper import SkillScraper, SkillScrapeError


class TestSkillScraperExtract:
    """测试 _extract_skill_data 静态方法。"""

    def test_extracts_skill_fields_from_valid_data(self):
        data = {
            "resource_id": 511,
            "name_code": 5124,
            "name_localkey": "灰姑娘",
            "skill1_detail": {
                "name_localkey": "無缺水晶",
                "info_description_localkey": "技能1",
                "description_localkey": "ATK ▲ {description_value_01}%",
                "description_value_list": [
                    {"description_value": ["1.7", "2.71"]},
                    {"description_value": ["10", "10"]},
                ],
            },
            "skill2_detail": {"name_localkey": "S2"},
            "ulti_skill_detail": {"name_localkey": "BS"},
            "extra_field": "should be excluded",
        }
        result = SkillScraper._extract_skill_data(data)
        assert result["resource_id"] == 511
        assert result["name_code"] == 5124
        assert result["name_localkey"] == "灰姑娘"
        assert result["skill1_detail"]["name_localkey"] == "無缺水晶"
        assert result["skill2_detail"]["name_localkey"] == "S2"
        assert result["ulti_skill_detail"]["name_localkey"] == "BS"
        assert "extra_field" not in result

    def test_returns_none_for_non_dict(self):
        assert SkillScraper._extract_skill_data([1, 2, 3]) is None
        assert SkillScraper._extract_skill_data("not a dict") is None

    def test_returns_none_when_no_skill1_detail(self):
        assert SkillScraper._extract_skill_data({"a": 1}) is None


class TestSkillScrapeError:
    def test_is_exception(self):
        err = SkillScrapeError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"
