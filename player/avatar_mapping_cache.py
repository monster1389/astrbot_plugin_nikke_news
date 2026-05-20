"""头像 URL 映射磁盘缓存：写入、加载、TTL 过期检查。"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from astrbot.api import logger

MAPPING_CACHE_VERSION = 1


class AvatarMappingCache:
    """头像映射 name_code → CDN URL 的磁盘持久化缓存。

    Attributes:
        _path: 缓存文件路径。
        _mappings: 内存中的 name_code → URL 映射。
    """

    def __init__(self, path: Path | None):
        self._path = path
        self._mappings: dict[int, str] = {}

    def load(self) -> dict[int, str]:
        """加载缓存，版本不匹配或损坏时返回空 dict。

        Returns:
            {name_code: CDN URL} 映射。
        """
        if not self._path or not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or data.get("version") != MAPPING_CACHE_VERSION
            ):
                return {}
            raw_mappings = data.get("mappings", {})
            if not isinstance(raw_mappings, dict):
                return {}
            self._mappings = {int(k): str(v) for k, v in raw_mappings.items() if v}
            return self._mappings
        except Exception as exc:
            logger.warning(f"NIKKE 头像映射缓存加载失败：{exc}")
            return {}

    def save(self, mappings: dict[int, str]) -> None:
        """保存映射到磁盘。

        Args:
            mappings: {name_code: CDN URL} 映射。
        """
        if not self._path:
            return
        data = {
            "version": MAPPING_CACHE_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "mappings": {str(k): v for k, v in mappings.items()},
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            logger.warning(f"NIKKE 头像映射缓存保存失败：{exc}")

    def is_stale(self, ttl_hours: int) -> bool:
        """检查缓存是否超过 TTL。

        Args:
            ttl_hours: TTL 小时数。

        Returns:
            True 表示缓存过期或文件不存在。
        """
        if not self._path or not self._path.exists():
            return True
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            updated_at = data.get("updated_at", "")
            if not updated_at:
                return True
            dt = datetime.fromisoformat(updated_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) - dt > timedelta(hours=ttl_hours)
        except Exception:
            return True
