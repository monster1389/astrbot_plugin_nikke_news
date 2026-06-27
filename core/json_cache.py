"""通用 JSON 磁盘缓存：版本校验、读写、TTL 过期判断。"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astrbot.api import logger

from core.utils import datetime_is_stale


class JsonCache:
    """泛型 JSON 磁盘缓存基类。

    子类覆盖 VERSION 控制版本失效。

    Attributes:
        _path: 缓存文件路径。
        _data: 内存中的缓存数据 dict。
    """

    VERSION: int = 0

    def __init__(self, path: Path | None):
        self._path = path
        self._data: dict[str, Any] = {}
        self._updated_at = ""

    def load(self) -> dict[str, Any]:
        """从磁盘加载缓存，版本不匹配或损坏返回空 dict。

        Returns:
            缓存数据 dict，无效时返回空 dict。
        """
        if not self._path or not self._path.exists():
            self._data = {}
            self._updated_at = ""
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("cache root is not an object")
            if self.VERSION > 0 and data.get("version") != self.VERSION:
                logger.info(
                    f"NIKKE 缓存版本不匹配，将重新刷新："
                    f"{data.get('version')} != {self.VERSION}"
                )
                self._data = {}
                self._updated_at = ""
                return {}
            self._data = data
            self._updated_at = str(data.get("updated_at", "") or "")
            return data
        except Exception as exc:
            logger.warning(f"NIKKE 缓存加载失败 ({self._path})：{exc}")
            self._data = {}
            self._updated_at = ""
            return {}

    def save(self, payload: dict[str, Any]) -> None:
        """写入缓存到磁盘，自动附加 version 和 updated_at。

        Args:
            payload: 待持久化的数据（不含 version/updated_at，由基类附加）。
        """
        if not self._path:
            return
        self._data = dict(payload)
        self._data["version"] = self.VERSION
        self._data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._updated_at = self._data["updated_at"]
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"NIKKE 缓存保存失败 ({self._path})：{exc}")

    def is_stale(self, ttl_hours: int) -> bool:
        """检查缓存是否超过 TTL。

        Args:
            ttl_hours: TTL 小时数。

        Returns:
            True 表示缓存过期或文件不存在。
        """
        if self._path and not self._path.exists():
            return True
        updated_at = self._updated_at
        if not updated_at and self._path:
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    updated_at = str(data.get("updated_at", ""))
            except Exception:
                return True
        return datetime_is_stale(updated_at, ttl_hours)

    def has_data(self) -> bool:
        """是否包含非空数据。"""
        return bool(self._data)
