from typing import Any

import httpx

from constants import (
    GET_USER_CHARACTERS_URL,
    GET_USER_CHARACTER_DETAILS_URL,
    PLAYER_PROGRESS_URL,
)
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

    async def fetch_characters(
        self, cookie: str, area_id: int = 84
    ) -> list[dict[str, Any]]:
        if not self._client:
            raise RuntimeError("http client not ready")

        headers = {"Cookie": cookie} if cookie else {}
        resp = await self._client.post(
            GET_USER_CHARACTERS_URL,
            headers=headers,
            json={"nikke_area_id": area_id},
        )
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, dict):
            raise RuntimeError("角色列表接口返回结构异常")

        code = safe_int(data.get("code"))
        if code != 0:
            raise RuntimeError(f"PLAYER_API_ERROR:{code}:{data.get('msg', '')}")

        characters = data.get("data", {}).get("characters")
        if not isinstance(characters, list):
            raise RuntimeError("角色列表缺少 characters 字段")

        return characters

    async def fetch_character_details(
        self, cookie: str, area_id: int, name_codes: list[int]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not self._client:
            raise RuntimeError("http client not ready")

        headers = {"Cookie": cookie} if cookie else {}
        resp = await self._client.post(
            GET_USER_CHARACTER_DETAILS_URL,
            headers=headers,
            json={"nikke_area_id": area_id, "name_codes": name_codes},
        )
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, dict):
            raise RuntimeError("角色详情接口返回结构异常")

        code = safe_int(data.get("code"))
        if code != 0:
            raise RuntimeError(f"PLAYER_API_ERROR:{code}:{data.get('msg', '')}")

        payload = data.get("data")
        if not isinstance(payload, dict):
            raise RuntimeError("角色详情缺少 data 字段")

        details = payload.get("character_details")
        if not isinstance(details, list):
            raise RuntimeError("角色详情缺少 character_details 字段")

        effects = payload.get("state_effects")
        if not isinstance(effects, list):
            effects = []

        return details, effects
