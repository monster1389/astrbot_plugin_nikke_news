from typing import Any

import httpx

from core.config import PluginConfig
from core.constants import OFFICIAL_PLATE_ID, POST_LIST_URL
from core.utils import safe_int


class NewsClient:
    """调用 Blablalink API 获取官方板块帖子列表。"""

    def __init__(self, client: httpx.AsyncClient | None, config: PluginConfig):
        self._client = client
        self._config = config

    async def fetch_official_posts(self) -> list[dict[str, Any]]:
        """POST 获取官方板块帖子，返回 data.post_list 或 []。"""
        if not self._client:
            return []

        payload = {
            "page": 1,
            "page_size": self._config.fetch_limit(),
            "plate_id": OFFICIAL_PLATE_ID,
            "area_id": "global",
            "lang": self._config.language(),
        }
        resp = await self._client.post(POST_LIST_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"Blablalink API 返回错误：{data}")

        items = data.get("data", {}).get("list", [])
        if not isinstance(items, list):
            raise RuntimeError(f"Blablalink API 结构异常：{data}")

        return [
            item
            for item in items
            if isinstance(item, dict)
            and safe_int(item.get("plate_id")) == OFFICIAL_PLATE_ID
            and safe_int(item.get("is_official")) == 1
            and item.get("post_uuid")
        ]
