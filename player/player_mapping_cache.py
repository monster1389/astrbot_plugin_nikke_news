"""角色映射缓存：角色名、词条选项的本地持久化与版本校验。"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astrbot.api import logger

from core.utils import datetime_is_stale


MAPPING_CACHE_VERSION = 2


class PlayerMappingCache:
    """管理角色名↔name_code 和词条 option 的缓存，支持版本校验。

    Attributes:
        _path: 缓存文件路径。
        _data: 内存中的缓存数据 dict。
    """

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
            "resource_ids": {},
        }

    @property
    def character_names(self) -> dict[int, str]:
        """name_code → 角色名映射。"""
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
        """反向映射：角色名 → name_code。"""
        result: dict[str, int] = {}
        for code, name in self.character_names.items():
            if name:
                result[name] = code
        return result

    @property
    def state_effect_options(self) -> dict[str, dict[str, Any]]:
        """词条 option ID → 元数据映射。"""
        raw = self._data.get("state_effect_options", {})
        return raw if isinstance(raw, dict) else {}

    @property
    def resource_ids(self) -> dict[int, int]:
        """name_code → resource_id 映射。"""
        raw = self._data.get("resource_ids", {})
        if not isinstance(raw, dict):
            return {}
        result: dict[int, int] = {}
        for code, rid in raw.items():
            try:
                result[int(code)] = int(rid)
            except (TypeError, ValueError):
                continue
        return result

    def load(self) -> bool:
        """从磁盘加载缓存，校验版本。

        Returns:
            True 表示加载成功且版本匹配。
        """
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
        resource_ids: dict[int, int] | None = None,
    ) -> None:
        """写入缓存到磁盘。

        Args:
            language: 语言代码。
            character_names: name_code → 角色名映射。
            state_effect_options: 词条 option 映射。
            sources: CDN 来源元数据（etag、last_modified），可选。
            resource_ids: name_code → resource_id 映射，可选。
        """
        self._data = {
            "version": MAPPING_CACHE_VERSION,
            "language": language,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "sources": sources or {},
            "character_names": {
                int(code): str(name) for code, name in character_names.items()
            },
            "state_effect_options": state_effect_options,
            "resource_ids": {
                int(code): int(rid) for code, rid in (resource_ids or {}).items()
            },
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
        """检查缓存是否超过 TTL。

        Args:
            ttl_hours: TTL 小时数。

        Returns:
            True 表示缓存过期或无效。
        """
        return datetime_is_stale(str(self._data.get("updated_at", "") or ""), ttl_hours)

    def has_useful_data(self) -> bool:
        """是否包含可用的角色名和词条数据。"""
        return bool(self.character_names) and bool(self.state_effect_options)
