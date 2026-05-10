import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from astrbot.api import logger


MAPPING_CACHE_VERSION = 1


class PlayerMappingCache:
    def __init__(self, path: Path | None):
        self._path = path
        self._data: dict[str, Any] = self._empty_data()

    @staticmethod
    def _empty_data() -> dict[str, Any]:
        return {
            "version": MAPPING_CACHE_VERSION,
            "language": "en",
            "updated_at": "",
            "sources": {},
            "characters": {},
            "state_effect_options": {},
        }

    @property
    def characters(self) -> dict[str, int]:
        raw = self._data.get("characters", {})
        if not isinstance(raw, dict):
            return {}
        result: dict[str, int] = {}
        for name, code in raw.items():
            try:
                result[str(name)] = int(code)
            except (TypeError, ValueError):
                continue
        return result

    @property
    def state_effect_options(self) -> dict[str, dict[str, Any]]:
        raw = self._data.get("state_effect_options", {})
        return raw if isinstance(raw, dict) else {}

    def load(self) -> bool:
        if not self._path or not self._path.exists():
            self._data = self._empty_data()
            return False
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("cache root is not an object")
            self._data = self._empty_data()
            self._data.update(data)
            return True
        except Exception as exc:
            logger.warning(f"NIKKE 玩家映射缓存加载失败：{exc}")
            self._data = self._empty_data()
            return False

    def save(
        self,
        *,
        language: str,
        characters: dict[str, int],
        state_effect_options: dict[str, dict[str, Any]],
        sources: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._data = {
            "version": MAPPING_CACHE_VERSION,
            "language": language,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "sources": sources or {},
            "characters": {name: int(code) for name, code in characters.items()},
            "state_effect_options": state_effect_options,
        }
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"NIKKE 玩家映射缓存保存失败：{exc}")

    def language_matches(self, language: str) -> bool:
        return str(self._data.get("language", "") or "") == language

    def is_stale(self, ttl_hours: int) -> bool:
        raw = str(self._data.get("updated_at", "") or "")
        if not raw:
            return True
        try:
            updated_at = datetime.fromisoformat(raw)
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
        except ValueError:
            return True
        return datetime.now(timezone.utc) - updated_at > timedelta(hours=ttl_hours)

    def has_useful_data(self, language: str) -> bool:
        return (
            self.language_matches(language)
            and bool(self.characters)
            and bool(self.state_effect_options)
        )

    def summary(self) -> str:
        return (
            f"角色 {len(self.characters)} 个，"
            f"词条 {len(self.state_effect_options)} 个"
        )
