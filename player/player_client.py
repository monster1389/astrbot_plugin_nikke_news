from typing import Any

import httpx

from core.constants import (
    DEFAULT_AREA_ID,
    DEFAULT_GAME_ID,
    GET_USER_CHARACTERS_URL,
    GET_USER_CHARACTER_DETAILS_URL,
    PLAYER_PROGRESS_URL,
)
from core.utils import safe_int


class PlayerClient:
    """调用 Blablalink 玩家数据 API（前哨收菜、角色列表、角色详情）。

    Attributes:
        _client: httpx AsyncClient 实例。
    """

    def __init__(self, client: httpx.AsyncClient | None):
        self._client = client

    @staticmethod
    def _validate_response(data: Any, label: str) -> dict[str, Any]:
        """校验 API 响应结构并提取 data 字段。

        Args:
            data: resp.json() 返回的原始数据。
            label: 中文接口名称（用于错误消息）。

        Returns:
            API 响应中的 data dict。

        Raises:
            RuntimeError: 结构异常或 code 非 0。
        """
        if not isinstance(data, dict):
            raise RuntimeError(f"{label}接口返回结构异常")

        code = safe_int(data.get("code"))
        if code != 0:
            raise RuntimeError(f"PLAYER_API_ERROR:{code}:{data.get('msg', '')}")

        payload = data.get("data")
        if not isinstance(payload, dict):
            raise RuntimeError(f"{label}缺少 data 字段")

        return payload

    async def fetch_progress(
        self, cookie: str, area_id: int = DEFAULT_AREA_ID
    ) -> dict[str, Any]:
        """获取日常进度数据。

        Args:
            cookie: 玩家 Cookie 字符串。
            area_id: 区域 ID，默认 84。

        Returns:
            包含 outpost_battle_storage_fullness 等字段的 data dict。

        Raises:
            RuntimeError: HTTP 请求失败、API 返回非 0 code、或响应结构异常。
        """
        if not self._client:
            raise RuntimeError("http client not ready")

        headers = {"Cookie": cookie} if cookie else {}
        resp = await self._client.post(
            PLAYER_PROGRESS_URL,
            headers=headers,
            json={"nikke_area_id": area_id},
        )
        resp.raise_for_status()
        return self._validate_response(resp.json(), "玩家数据")

    async def fetch_characters(
        self,
        cookie: str,
        area_id: int = DEFAULT_AREA_ID,
        *,
        language: str = "en",
        game_id: str = DEFAULT_GAME_ID,
    ) -> list[dict[str, Any]]:
        """获取玩家拥有的角色列表。

        Args:
            cookie: 玩家 Cookie 字符串。
            area_id: 区域 ID，默认 84。
            language: 接口语言，默认 en。
            game_id: 游戏 ID，默认 29080。

        Returns:
            角色 dict 列表（含 name_code、combat 等字段）。

        Raises:
            RuntimeError: 请求失败或响应结构异常。
        """
        if not self._client:
            raise RuntimeError("http client not ready")

        headers = _player_headers(cookie, language, game_id)
        resp = await self._client.post(
            GET_USER_CHARACTERS_URL,
            headers=headers,
            json={"nikke_area_id": area_id},
        )
        resp.raise_for_status()
        payload = self._validate_response(resp.json(), "角色列表")

        characters = payload.get("characters")
        if not isinstance(characters, list):
            raise RuntimeError("角色列表缺少 characters 字段")

        return characters

    async def fetch_character_details(
        self,
        cookie: str,
        area_id: int,
        name_codes: list[int],
        *,
        intl_open_id: str = "",
        language: str = "en",
        game_id: str = DEFAULT_GAME_ID,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """获取指定角色详情。

        Args:
            cookie: 玩家 Cookie 字符串。
            area_id: 区域 ID。
            name_codes: 角色 name_code 列表。
            intl_open_id: 国际版 Open ID，可选。
            language: 接口语言，默认 en。
            game_id: 游戏 ID，默认 29080。

        Returns:
            (character_details 列表, state_effects 列表) 元组。

        Raises:
            RuntimeError: 请求失败或响应结构异常。
        """
        if not self._client:
            raise RuntimeError("http client not ready")

        headers = _player_headers(cookie, language, game_id)
        payload: dict[str, Any] = {"nikke_area_id": area_id, "name_codes": name_codes}
        if intl_open_id:
            payload["intl_open_id"] = intl_open_id
        resp = await self._client.post(
            GET_USER_CHARACTER_DETAILS_URL,
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = self._validate_response(resp.json(), "角色详情")

        details = data.get("character_details")
        if not isinstance(details, list):
            raise RuntimeError("角色详情缺少 character_details 字段")

        effects = data.get("state_effects")
        if not isinstance(effects, list):
            effects = []

        return details, effects


def _player_headers(cookie: str, language: str, game_id: str) -> dict[str, str]:
    """构建玩家 API 请求头（x-language、x-common-params、Cookie）。"""
    headers = {
        "x-language": language,
        "x-channel-type": "2",
        "x-common-params": (
            '{"game_id":"16","area_id":"global","source":"pc_web",'
            f'"intl_game_id":"{game_id or DEFAULT_GAME_ID}","language":"{language}",'
            '"env":"prod","data_statistics_scene":"outer",'
            '"data_statistics_page_id":"https://www.blablalink.com/shiftyspad/nikke-list",'
            '"data_statistics_client_type":"pc_web",'
            f'"data_statistics_lang":"{language}"'
            "}"
        ),
    }
    if cookie:
        headers["Cookie"] = cookie
    return headers
