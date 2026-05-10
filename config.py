import json
from datetime import time

from astrbot.api import AstrBotConfig, logger

from constants import CONTENT_MODES, SUPPORTED_LANGUAGES

_PLAYER_MAPPING_LANGUAGES = {"en", "zh", "zh-TW", "ja", "ko"}


class PluginConfig:
    def __init__(self, config: AstrBotConfig | None):
        self._config = config or {}
        self._news = self._as_dict(self._config.get("news_push"))
        self._player = self._as_dict(self._config.get("player_reminder"))
        if self._config.get("news_push") is not None and not isinstance(
            self._config.get("news_push"), dict
        ):
            logger.warning("NIKKE 配置 news_push 结构无效，已使用默认值。")
        if self._config.get("player_reminder") is not None and not isinstance(
            self._config.get("player_reminder"), dict
        ):
            logger.warning("NIKKE 配置 player_reminder 结构无效，已使用默认值。")

    @staticmethod
    def _as_dict(value: object) -> dict:
        return value if isinstance(value, dict) else {}

    def news_config(self) -> dict:
        return self._news

    def config_bool(self, key: str, default: bool) -> bool:
        value = self._config.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def config_int(self, key: str, default: int) -> int:
        try:
            return int(self._config.get(key, default))
        except (TypeError, ValueError):
            logger.warning(f"NIKKE 配置 {key} 非法，已使用默认值 {default}。")
            return default

    def poll_interval_seconds(self) -> int:
        return max(60, self.config_int("poll_interval_seconds", 300))

    def fetch_limit(self) -> int:
        return min(50, max(1, self._news_int("fetch_limit", 10)))

    def language(self) -> str:
        language = str(self._news.get("language", "zh-TW")).strip() or "zh-TW"
        if language not in SUPPORTED_LANGUAGES:
            logger.warning(f"NIKKE 语言配置无效，已使用 zh-TW：{language}")
            return "zh-TW"
        return language

    def push_delay_seconds(self) -> int:
        return min(30, max(0, self._news_int("push_delay_seconds", 2)))

    def push_prefix(self) -> str:
        return str(self._news.get("push_prefix", "") or "").strip()

    def content_mode(self) -> str:
        mode = str(self._news.get("content_mode", "summary") or "summary").strip()
        if mode not in CONTENT_MODES:
            logger.warning(f"NIKKE 内容模式配置无效，已使用 summary：{mode}")
            return "summary"
        return mode

    def max_images(self) -> int:
        return min(9, max(0, self._news_int("max_images", 3)))

    def show_publish_time(self) -> bool:
        return self._nested_bool(self._news, "show_publish_time", True)

    def player_data_enabled(self) -> bool:
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
        cfg = self._parse_cookie_json()
        if cfg:
            try:
                return int(cfg.get("nikke_area_id", 84))
            except (TypeError, ValueError):
                pass
        return 84

    def player_open_id(self) -> str:
        cfg = self._parse_cookie_json()
        value = str(cfg.get("game_openid", "") or "").strip() if cfg else ""
        if value:
            return value
        return self._cookie_header_value("game_openid")

    def player_game_id(self) -> str:
        cfg = self._parse_cookie_json()
        value = str(cfg.get("game_gameid", "") or "").strip() if cfg else ""
        if value:
            return value
        return self._cookie_header_value("game_gameid") or "29080"

    def player_mapping_language(self) -> str:
        language = str(self._player.get("mapping_language", "en") or "en").strip()
        if language not in _PLAYER_MAPPING_LANGUAGES:
            logger.warning(f"NIKKE 玩家映射语言配置无效，已使用 en：{language}")
            return "en"
        return language

    def player_mapping_cache_ttl_hours(self) -> int:
        return max(1, self._player_int("mapping_cache_ttl_hours", 168))

    def player_auto_refresh_mapping(self) -> bool:
        return self._nested_bool(self._player, "auto_refresh_mapping", True)

    def character_list_url(self) -> str:
        return str(self._player.get("character_list_url", "") or "").strip()

    def character_aliases(self) -> dict[str, list[str]]:
        """Parse character_alias config into a normalized dict.

        Accepts both a native dict (from JSON config) and a JSON string
        (from the text editor), mirroring _parse_cookie_json().
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
        return self._nested_bool(self._player, "daily_mission_enabled", True)

    def outpost_fullness_threshold_percent(self) -> int:
        threshold = self._player_int("outpost_fullness_threshold_percent", 90)
        return min(100, max(0, threshold))

    def player_daily_mission_remind_time(self) -> time:
        raw = str(self._player.get("daily_mission_remind_time", "21:00") or "21:00").strip()
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
        return str(self._player.get("alert_prefix", "【NIKKE 玩家状态提醒】") or "").strip()

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
        return self._nested_int(self._news, key, default, f"news_push.{key}")

    def _player_int(self, key: str, default: int) -> int:
        return self._nested_int(self._player, key, default, f"player_reminder.{key}")
