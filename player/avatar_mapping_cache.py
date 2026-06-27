"""头像 URL 映射磁盘缓存：写入、加载、TTL 过期检查。"""

from core.json_cache import JsonCache


class AvatarMappingCache(JsonCache):
    """头像映射 name_code → CDN URL 的磁盘持久化缓存。

    Attributes:
        _path: 缓存文件路径。
        _data: 内存中的缓存数据 dict。
    """

    VERSION = 1

    @property
    def mappings(self) -> dict[int, str]:
        """name_code → CDN URL 映射。"""
        raw_mappings = self._data.get("mappings", {})
        if not isinstance(raw_mappings, dict):
            return {}
        return {int(k): str(v) for k, v in raw_mappings.items() if v}

    def load(self) -> dict[int, str]:
        """加载缓存，版本不匹配或损坏时返回空 dict。

        Returns:
            {name_code: CDN URL} 映射。
        """
        super().load()
        return self.mappings

    def save(self, mappings: dict[int, str]) -> None:
        """保存映射到磁盘。

        Args:
            mappings: {name_code: CDN URL} 映射。
        """
        super().save({"mappings": {str(k): v for k, v in mappings.items()}})
