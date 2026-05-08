from datetime import time

from astrbot.api import AstrBotConfig, logger

from constants import CONTENT_MODES, SUPPORTED_LANGUAGES


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

    def player_data_cookie(self) -> str:
        return str(self._player.get("cookie", "") or "").strip()

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
