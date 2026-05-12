import json
from pathlib import Path
from typing import Any

from astrbot.api import logger

from .constants import MAX_SEEN_POSTS


class PluginStateStore:
    def __init__(self, state_path: Path | None):
        self._state_path = state_path

    @staticmethod
    def default_state() -> dict[str, Any]:
        return {
            "initialized": False,
            "seen_post_uuids": [],
            "player_alert_state": {
                "cookie_invalid_notified": False,
                "last_outpost_alert_day_key": "",
                "last_daily_mission_alert_day_key": "",
            },
        }

    @classmethod
    def normalize_state(cls, data: Any) -> dict[str, Any]:
        state = cls.default_state()
        if not isinstance(data, dict):
            return state

        seen = data.get("seen_post_uuids", [])
        if not isinstance(seen, list):
            seen = []
        state["initialized"] = bool(data.get("initialized", False))
        state["seen_post_uuids"] = [str(item) for item in seen if item]

        player_raw = data.get("player_alert_state", {})
        if not isinstance(player_raw, dict):
            player_raw = {}
        state["player_alert_state"] = {
            "cookie_invalid_notified": bool(
                player_raw.get("cookie_invalid_notified", False)
            ),
            "last_outpost_alert_day_key": str(
                player_raw.get("last_outpost_alert_day_key", "") or ""
            ),
            "last_daily_mission_alert_day_key": str(
                player_raw.get("last_daily_mission_alert_day_key", "") or ""
            ),
        }
        return state

    def load(self) -> dict[str, Any]:
        if not self._state_path or not self._state_path.exists():
            return self.default_state()

        try:
            with self._state_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return self.normalize_state(data)
        except Exception as exc:
            logger.warning(f"NIKKE 状态文件读取失败，将重新初始化：{exc}")
            return self.default_state()

    def save(self, state: dict[str, Any]):
        if not self._state_path:
            return

        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            with self._state_path.open("w", encoding="utf-8") as f:
                json.dump(self.normalize_state(state), f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning(f"NIKKE 状态文件保存失败：{exc}")

    @staticmethod
    def mark_seen(state: dict[str, Any], post_uuids: list[str]):
        current = [str(item) for item in state.get("seen_post_uuids", []) if item]
        for post_uuid in post_uuids:
            post_uuid = str(post_uuid)
            if post_uuid in current:
                current.remove(post_uuid)
            current.append(post_uuid)
        state["seen_post_uuids"] = current[-MAX_SEEN_POSTS:]
