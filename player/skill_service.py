"""技能描述查询服务：缓存管理、Playwright 抓取编排、格式化输出。"""

import re
from pathlib import Path
from typing import Any

import httpx
from astrbot.api import logger

from core.json_cache import JsonCache
from core.utils import safe_int
from player.player_client import PlayerClient
from player.skill_scraper import SkillScraper, SkillScrapeError


class SkillError(Exception):
    """技能查询错误，包含面向用户的中文消息。"""

    def __init__(self, message: str):
        self.message = message


class SkillService:
    """角色技能查询：缓存检查 → Playwright 抓取 → API 等级 → 格式化。

    Attributes:
        _data_dir: 插件数据目录。
        _skills_dir: 技能缓存目录。
        _client: httpx AsyncClient 实例。
        _config: 插件配置实例。
        _mapping_cache: 玩家映射缓存（提供 resource_ids）。
        _scraper: Playwright 技能抓取器。
        _ttl_hours: 缓存 TTL 小时数。
    """

    def __init__(
        self,
        data_dir: Path,
        client: httpx.AsyncClient,
        config: Any,
        mapping_cache: Any,
        ttl_hours: int,
    ):
        self._data_dir = data_dir
        self._skills_dir = data_dir / "skills"
        self._client = client
        self._config = config
        self._mapping_cache = mapping_cache
        self._scraper = SkillScraper()
        self._ttl_hours = ttl_hours

    def _ensure_skills_dir(self) -> None:
        """确保 skills/ 目录存在。"""
        try:
            self._skills_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning(f"NIKKE 技能缓存目录创建失败：{exc}")

    def _cache_path(self, name_code: int, language: str) -> Path:
        """返回技能缓存文件路径。

        Args:
            name_code: 角色 name_code。
            language: 语言代码。

        Returns:
            skills/{name_code}_{language}.json 路径。
        """
        return self._skills_dir / f"{name_code}_{language}.json"

    def _load_cache(self, name_code: int, language: str) -> dict[str, Any] | None:
        """加载技能缓存，过期或损坏返回 None。

        Args:
            name_code: 角色 name_code。
            language: 语言代码。

        Returns:
            技能数据 dict，无效时返回 None。
        """
        path = self._cache_path(name_code, language)
        cache = JsonCache(path)
        data = cache.load()
        if not data:
            return None
        if cache.is_stale(self._ttl_hours):
            return None
        if "skill1_detail" not in data:
            return None
        return data

    def _save_cache(
        self, name_code: int, language: str, skill_data: dict[str, Any]
    ) -> None:
        """保存技能缓存到磁盘。

        Args:
            name_code: 角色 name_code。
            language: 语言代码。
            skill_data: 技能数据 dict。
        """
        self._ensure_skills_dir()
        path = self._cache_path(name_code, language)
        cache = JsonCache(path)
        cache.save(skill_data)

    def is_cached(self, name_code: int, language: str | None = None) -> bool:
        """检查指定角色的技能数据是否已缓存且未过期。

        Args:
            name_code: 角色 name_code。
            language: 语言代码，为 None 时从 config 读取。

        Returns:
            True 表示缓存有效。
        """
        if language is None:
            language = self._config.player_mapping_language()
        return self._load_cache(name_code, language) is not None

    async def get_skill_text(
        self,
        cookie: str,
        name_code: int,
        display_name: str,
        area_id: int,
        language: str,
        game_id: str,
    ) -> str:
        """获取角色技能描述文本。

        Args:
            cookie: 玩家 Cookie。
            name_code: 角色 name_code。
            display_name: 角色显示名。
            area_id: 区域 ID。
            language: 查询语言。
            game_id: 游戏 ID。

        Returns:
            格式化后的技能描述文本。

        Raises:
            SkillError: resource_id 缺失、抓取失败、API 失败。
        """
        skill_data = self._load_cache(name_code, language)

        if skill_data is None:
            resource_id = self._mapping_cache.resource_ids.get(name_code)
            if resource_id is None:
                raise SkillError(
                    "未找到角色 resource_id，请先执行 /nikke_refresh 刷新角色映射。"
                )
            try:
                skill_data = await self._scraper.scrape(resource_id, language)
            except SkillScrapeError as exc:
                raise SkillError(str(exc))
            self._save_cache(name_code, language, skill_data)

        player = PlayerClient(self._client)
        try:
            details, _ = await player.fetch_character_details(
                cookie,
                area_id,
                [name_code],
                intl_open_id=self._config.player_open_id(),
                language=language,
                game_id=game_id,
            )
        except Exception as exc:
            logger.warning(f"NIKKE 角色详情查询失败：{exc}")
            raise SkillError(f"角色详情查询失败：{exc}")

        if not details:
            raise SkillError(f"未在账号中找到角色「{display_name}」。")

        char_detail = details[0]
        levels = {
            "skill1": safe_int(
                char_detail.get("skill1_lv", char_detail.get("s1_lv", 1))
            ),
            "skill2": safe_int(
                char_detail.get("skill2_lv", char_detail.get("s2_lv", 1))
            ),
            "burst": safe_int(
                char_detail.get(
                    "ulti_skill_lv",
                    char_detail.get("burst_skill_lv", char_detail.get("s3_lv", 1)),
                )
            ),
        }

        return self._format_skills(skill_data, levels, display_name)

    @staticmethod
    def _strip_tags(text: str) -> str:
        """去除 <color=...> 和 <word_group=...> 标签，保留内容文本。

        Args:
            text: 含标签的原始文本。

        Returns:
            去除标签后的纯文本。
        """
        text = re.sub(r"</?color[^>]*>", "", text)
        text = re.sub(r"</?word_group[^>]*>", "", text)
        return text

    @staticmethod
    def _format_skills(
        skill_data: dict[str, Any],
        levels: dict[str, int],
        display_name: str,
    ) -> str:
        """将技能模板和等级数值合并格式化为最终输出文本。

        Args:
            skill_data: 含 skill1/2/ulti_detail 的 dict。
            levels: {"skill1": int, "skill2": int, "burst": int}。
            display_name: 角色显示名。

        Returns:
            格式化后的多技能描述文本。
        """
        skill_configs = [
            ("skill1_detail", "skill1"),
            ("skill2_detail", "skill2"),
            ("ulti_skill_detail", "burst"),
        ]

        parts: list[str] = [display_name]

        for detail_key, level_key in skill_configs:
            detail = skill_data.get(detail_key)
            if not isinstance(detail, dict):
                continue

            name = detail.get("name_localkey", "")
            info = detail.get("info_description_localkey", "")
            template = detail.get("description_localkey", "")
            value_list = detail.get("description_value_list", [])

            level = max(1, min(levels.get(level_key, 1), 10))
            level_index = level - 1

            header = f"{info} — {name}" if info else name
            desc = template
            for i, item in enumerate(value_list):
                if not isinstance(item, dict):
                    continue
                values = item.get("description_value", [])
                if not values:
                    continue
                placeholder = f"{{description_value_{i + 1:02d}}}"
                val = values[level_index] if level_index < len(values) else values[-1]
                desc = desc.replace(placeholder, str(val))

            desc = SkillService._strip_tags(desc)
            parts.append(f"\n{header}")
            parts.append(desc)

        return "\n".join(parts)
