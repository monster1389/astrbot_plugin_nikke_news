"""角色映射缓存：角色名、词条选项的本地持久化与版本校验。"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from astrbot.api import logger


MAPPING_CACHE_VERSION = 2


class PlayerMappingCache:
    """管理角色名↔name_code 和词条 option 的缓存，支持版本校验。"""

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
            "character_names": {},
            "state_effect_options": {},
        }

    @property
    def character_names(self) -> dict[int, str]:
        raw = self._data.get("character_names", {})
        if not isinstance(raw, dict):
            return {}
        result: dict[int, str] = {}
        for code, name in raw.items():
            try:
                result[int(code)] = str(name)
            except (TypeError, ValueError):
                continue
        return result

    def name_to_code(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for code, name in self.character_names.items():
            if name:
                result[name] = code
        return result

    @property
    def state_effect_options(self) -> dict[str, dict[str, Any]]:
        raw = self._data.get("state_effect_options", {})
        return raw if isinstance(raw, dict) else {}

    def load(self) -> bool:
        """从磁盘加载缓存，校验版本，版本不匹配或损坏时从空数据开始。"""
        if not self._path or not self._path.exists():
            self._data = self._empty_data()
            return False
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("cache root is not an object")
            if data.get("version") != MAPPING_CACHE_VERSION:
                logger.info(
                    f"NIKKE 玩家映射缓存版本不匹配，将重新刷新："
                    f"{data.get('version')} != {MAPPING_CACHE_VERSION}"
                )
                self._data = self._empty_data()
                return False
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
        character_names: dict[int, str],
        state_effect_options: dict[str, dict[str, Any]],
        sources: dict[str, dict[str, str]] | None = None,
    ) -> None:
        """写入缓存到磁盘，失败时删除坏文件。"""
        self._data = {
            "version": MAPPING_CACHE_VERSION,
            "language": language,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "sources": sources or {},
            "character_names": {
                int(code): str(name) for code, name in character_names.items()
            },
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

    def has_useful_data(self) -> bool:
        return bool(self.character_names) and bool(self.state_effect_options)
