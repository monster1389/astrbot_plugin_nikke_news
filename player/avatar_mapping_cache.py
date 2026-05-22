"""头像 URL 映射磁盘缓存：写入、加载、TTL 过期检查。"""

import json
from datetime import datetime, timezone
from pathlib import Path

from astrbot.api import logger

from core.utils import datetime_is_stale

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
        self._updated_at = ""

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
            self._updated_at = str(data.get("updated_at", ""))
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
        self._updated_at = datetime.now(timezone.utc).isoformat()
        data = {
            "version": MAPPING_CACHE_VERSION,
            "updated_at": self._updated_at,
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
        """检查缓存是否超过 TTL，优先使用内存中的 updated_at。

        Args:
            ttl_hours: TTL 小时数。

        Returns:
            True 表示缓存过期或文件不存在。
        """
        if not self._path or not self._path.exists():
            return True
        if self._updated_at:
            return datetime_is_stale(self._updated_at, ttl_hours)
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._updated_at = str(data.get("updated_at", ""))
            return datetime_is_stale(self._updated_at, ttl_hours)
        except Exception:
            return True
