"""插件配置封装，从 AstrBot 配置字典中读取各类参数。"""

import json
from datetime import time
from typing import Any

from astrbot.api import AstrBotConfig, logger

from .constants import CONTENT_MODES, SUPPORTED_LANGUAGES

_PLAYER_MAPPING_LANGUAGES = {"en", "zh-TW", "ja", "ko"}


class PluginConfig:
    """从 AstrBot 配置字典读取新闻推送与玩家数据的各项参数。

    Attributes:
        _config: 原始 AstrBot 配置字典。
        _news: 新闻板块配置子字典。
        _player: 玩家板块配置子字典（含状态提醒和 nikke 查询）。
    """

    def __init__(self, config: AstrBotConfig | None):
        self._config = config or {}
        self._news = self._as_dict(self._config.get("新闻"))
        player_section = self._as_dict(self._config.get("玩家"))
        self._player: dict[str, Any] = {}
        for key, value in player_section.items():
            if not isinstance(value, dict):
                self._player[key] = value
        self._player.update(self._as_dict(player_section.get("状态提醒")))
        self._player.update(self._as_dict(player_section.get("nikke查询")))
        if self._config.get("新闻") is not None and not isinstance(
            self._config.get("新闻"), dict
        ):
            logger.warning("NIKKE 配置 新闻 结构无效，已使用默认值。")
        if self._config.get("玩家") is not None and not isinstance(
            self._config.get("玩家"), dict
        ):
            logger.warning("NIKKE 配置 玩家 结构无效，已使用默认值。")

    @staticmethod
    def _as_dict(value: object) -> dict:
        return value if isinstance(value, dict) else {}

    def news_config(self) -> dict:
        """返回新闻板块配置子字典。"""
        return self._news

    def config_bool(self, key: str, default: bool) -> bool:
        """读取布尔型配置项，支持顶层和新闻板块回退。

        Args:
            key: 配置键名。
            default: 默认值。

        Returns:
            解析后的布尔值。
        """
        value = self._config.get(key)
        if value is None:
            value = self._news.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def config_int(self, key: str, default: int) -> int:
        """读取整型配置项，支持顶层和新闻板块回退。

        Args:
            key: 配置键名。
            default: 默认值。

        Returns:
            解析后的整数值，解析失败时返回默认值。
        """
        try:
            value = self._config.get(key)
            if value is None:
                value = self._news.get(key, default)
            return int(value)
        except (TypeError, ValueError):
            logger.warning(f"NIKKE 配置 {key} 非法，已使用默认值 {default}。")
            return default

    def poll_interval_seconds(self) -> int:
        """返回轮询间隔秒数，下限 60s。"""
        return max(60, self.config_int("poll_interval_seconds", 300))

    def fetch_limit(self) -> int:
        """返回每次拉取帖子数量上限，范围 1-50。"""
        return min(50, max(1, self._news_int("fetch_limit", 10)))

    def language(self) -> str:
        """返回新闻语言代码，无效值时回退 en。"""
        language = str(self._news.get("language", "en")).strip() or "en"
        if language not in SUPPORTED_LANGUAGES:
            logger.warning(f"NIKKE 语言配置无效，已使用 en：{language}")
            return "en"
        return language

    def push_delay_seconds(self) -> int:
        """返回多条推送之间的间隔秒数，范围 0-30。"""
        return min(30, max(0, self._news_int("push_delay_seconds", 2)))

    def push_prefix(self) -> str:
        """返回推送消息前缀字符串。"""
        return str(self._news.get("push_prefix", "") or "").strip()

    def content_mode(self) -> str:
        """返回内容展示模式（none/summary/content），无效值时回退 summary。"""
        mode = str(self._news.get("content_mode", "summary") or "summary").strip()
        if mode not in CONTENT_MODES:
            logger.warning(f"NIKKE 内容模式配置无效，已使用 summary：{mode}")
            return "summary"
        return mode

    def max_images(self) -> int:
        """返回每条推送附带图片数量上限，范围 0-9。"""
        return min(9, max(0, self._news_int("max_images", 3)))

    def show_publish_time(self) -> bool:
        """返回是否在推送中显示发布时间。"""
        return self._nested_bool(self._news, "show_publish_time", True)

    def player_data_enabled(self) -> bool:
        """返回玩家数据功能是否启用。"""
        return self._nested_bool(self._player, "enabled", False)

    def _parse_cookie_json(self) -> dict:
        """Parse the cookie config value into a dict, regardless of input format."""
        cookie_cfg = self._player.get("cookie")
        if isinstance(cookie_cfg, dict):
            return cookie_cfg
        if isinstance(cookie_cfg, str) and cookie_cfg.strip():
            try:
                parsed = json.loads(cookie_cfg)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        return {}

    def player_data_cookie(self) -> str:
        """返回玩家数据请求的 Cookie 字符串。

        优先从结构化 JSON 拼装，回退到旧版纯文本 Cookie。
        """
        cfg = self._parse_cookie_json()
        if cfg:
            parts = []
            for key in ("game_token", "game_openid", "game_channelid", "game_gameid"):
                value = str(cfg.get(key, "") or "").strip()
                if value:
                    parts.append(f"{key}={value}")
            if parts:
                return "; ".join(parts)
        # Fallback: plain string cookie (backward compat)
        cookie_cfg = self._player.get("cookie")
        if isinstance(cookie_cfg, str) and cookie_cfg.strip():
            return cookie_cfg.strip()
        return ""

    def player_data_area_id(self) -> int:
        """返回玩家数据区域 ID，默认 84。"""
        cfg = self._parse_cookie_json()
        if cfg:
            try:
                return int(cfg.get("nikke_area_id", 84))
            except (TypeError, ValueError):
                pass
        return 84

    def player_open_id(self) -> str:
        """返回玩家 Open ID，优先从结构化 JSON 读取。"""
        cfg = self._parse_cookie_json()
        value = str(cfg.get("game_openid", "") or "").strip() if cfg else ""
        if value:
            return value
        return self._cookie_header_value("game_openid")

    def player_game_id(self) -> str:
        """返回游戏 ID，默认 29080。"""
        cfg = self._parse_cookie_json()
        value = str(cfg.get("game_gameid", "") or "").strip() if cfg else ""
        if value:
            return value
        return self._cookie_header_value("game_gameid") or "29080"

    def player_mapping_language(self) -> str:
        """返回角色映射语言代码，无效值时回退 zh-TW。"""
        language = str(self._player.get("mapping_language", "zh-TW") or "zh-TW").strip()
        if language not in _PLAYER_MAPPING_LANGUAGES:
            logger.warning(f"NIKKE 玩家映射语言配置无效，已使用 zh-TW：{language}")
            return "zh-TW"
        return language

    def player_mapping_cache_ttl_hours(self) -> int:
        """返回映射缓存 TTL 小时数，下限 1h。"""
        return max(1, self._player_int("mapping_cache_ttl_hours", 168))

    def player_auto_refresh_mapping(self) -> bool:
        """返回是否在查询时自动刷新过期映射。"""
        return self._nested_bool(self._player, "auto_refresh_mapping", True)

    def character_aliases(self) -> dict[str, list[str]]:
        """解析角色别名配置为规范化的 dict。

        支持 dict 和 JSON 字符串两种输入格式。

        Returns:
            {英文名: [别名列表]}，解析失败返回空 dict。
        """
        cfg = self._player.get("character_alias")
        if isinstance(cfg, dict):
            return self._normalize_aliases(cfg)
        if isinstance(cfg, str) and cfg.strip():
            try:
                parsed = json.loads(cfg)
                if isinstance(parsed, dict):
                    return self._normalize_aliases(parsed)
            except json.JSONDecodeError:
                logger.warning("NIKKE 角色别名 JSON 解析失败，已忽略。")
        return {}

    @staticmethod
    def _normalize_aliases(raw: dict) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for name, aliases in raw.items():
            name_key = str(name).strip()
            if not name_key:
                continue
            if isinstance(aliases, list):
                result[name_key] = [str(a).strip() for a in aliases if str(a).strip()]
            elif isinstance(aliases, str):
                result[name_key] = [aliases.strip()] if aliases.strip() else []
        return {k: v for k, v in result.items() if v}

    def player_remind_daily_mission_enabled(self) -> bool:
        """返回日常任务提醒是否启用。"""
        return self._nested_bool(self._player, "daily_mission_enabled", True)

    def outpost_fullness_threshold_percent(self) -> int:
        """返回前哨满仓提醒阈值百分比，范围 0-100。"""
        threshold = self._player_int("outpost_fullness_threshold_percent", 90)
        return min(100, max(0, threshold))

    def player_daily_mission_remind_time(self) -> time:
        """返回日常任务提醒时间，无效值时回退 21:00。"""
        raw = str(
            self._player.get("daily_mission_remind_time", "21:00") or "21:00"
        ).strip()
        try:
            hour_text, minute_text = raw.split(":", 1)
            hour = int(hour_text)
            minute = int(minute_text)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return time(hour=hour, minute=minute)
            raise ValueError("out of range")
        except Exception:
            logger.warning(f"NIKKE 玩家提醒时间配置无效，已使用 21:00：{raw}")
            return time(hour=21, minute=0)

    def player_alert_prefix(self) -> str:
        """返回玩家提醒消息前缀字符串。"""
        return str(
            self._player.get("alert_prefix", "【NIKKE 玩家状态提醒】") or ""
        ).strip()

    def show_character_avatar(self) -> bool:
        """返回是否在角色查询结果中展示头像。"""
        return self._nested_bool(self._player, "show_character_portrait", True)

    def _cookie_header_value(self, key: str) -> str:
        cookie = self.player_data_cookie()
        for part in cookie.split(";"):
            if "=" not in part:
                continue
            name, value = part.split("=", 1)
            if name.strip() == key:
                return value.strip()
        return ""

    def _nested_bool(self, source: dict, key: str, default: bool) -> bool:
        value = source.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _nested_int(self, source: dict, key: str, default: int, label: str) -> int:
        try:
            return int(source.get(key, default))
        except (TypeError, ValueError):
            logger.warning(f"NIKKE 配置 {label} 非法，已使用默认值 {default}。")
            return default

    def _news_int(self, key: str, default: int) -> int:
        return self._nested_int(self._news, key, default, f"新闻.{key}")

    def _player_int(self, key: str, default: int) -> int:
        return self._nested_int(self._player, key, default, f"玩家.{key}")
