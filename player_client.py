from typing import Any

import httpx

from constants import PLAYER_PROGRESS_URL
from utils import safe_int


class PlayerClient:
    def __init__(self, client: httpx.AsyncClient | None):
        self._client = client

    async def fetch_progress(self, cookie: str, area_id: int = 84) -> dict[str, Any]:
        if not self._client:
            raise RuntimeError("http client not ready")

        headers = {"Cookie": cookie} if cookie else {}
        resp = await self._client.post(
            PLAYER_PROGRESS_URL,
            headers=headers,
            json={"nikke_area_id": area_id},
        )
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, dict):
            raise RuntimeError("玩家数据接口返回结构异常")

        code = safe_int(data.get("code"))
        if code != 0:
            raise RuntimeError(f"PLAYER_API_ERROR:{code}:{data.get('msg', '')}")

        payload = data.get("data")
        if not isinstance(payload, dict):
            raise RuntimeError("玩家数据缺少 data 字段")

        return payload
