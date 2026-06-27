"""角色映射缓存：角色名、词条选项的本地持久化与版本校验。"""

from pathlib import Path
from typing import Any

from core.json_cache import JsonCache


class PlayerMappingCache(JsonCache):
    """管理角色名↔name_code 和词条 option 的缓存。

    Attributes:
        _path: 缓存文件路径。
        _data: 内存中的缓存数据 dict。
    """

    VERSION = 2

    def __init__(self, path: Path | None):
        super().__init__(path)

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
            sources: CDN 来源元数据，可选。
            resource_ids: name_code → resource_id 映射，可选。
        """
        super().save(
            {
                "language": language,
                "sources": sources or {},
                "character_names": {
                    int(code): str(name) for code, name in character_names.items()
                },
                "state_effect_options": state_effect_options,
                "resource_ids": {
                    int(code): int(rid)
                    for code, rid in (resource_ids or {}).items()
                },
            }
        )

    def has_useful_data(self) -> bool:
        """是否包含可用的角色名和词条数据。"""
        return bool(self.character_names) and bool(self.state_effect_options)
