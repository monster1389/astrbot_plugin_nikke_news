from typing import Any

import httpx
from astrbot.api import logger

from character_map import CharacterMap
from config import PluginConfig
from message_builder import MessageBuilder
from player_client import PlayerClient


class CharacterQueryError(Exception):
    def __init__(self, message: str):
        self.message = message


class CharacterService:
    def __init__(
        self,
        client: httpx.AsyncClient,
        character_map: CharacterMap,
        config: PluginConfig,
    ):
        self._client = client
        self._character_map = character_map
        self._config = config

    async def query(self, name: str) -> str:
        cookie = self._config.player_data_cookie()
        if not cookie:
            raise CharacterQueryError(
                "未配置玩家 Cookie，无法查询角色数据。"
                "请先在插件配置中设置 player_reminder.cookie。"
            )

        if not self._character_map.is_loaded:
            raise CharacterQueryError(
                "角色数据尚未加载，请检查 character_map.json 是否存在，"
                "或配置 character_list_url 后执行 /nikke refresh。"
            )

        matches = self._character_map.lookup(name)
        if not matches:
            raise CharacterQueryError(f"未找到角色「{name}」，请检查名称是否正确。")

        if len(matches) > 1:
            names = "、".join(f"「{n}」" for _, n in matches[:10])
            hint = "\n请提供更精确的名称。" if len(matches) > 10 else ""
            raise CharacterQueryError(f"找到 {len(matches)} 个匹配：\n{names}{hint}")

        name_code, en_name = matches[0]
        area_id = self._config.player_data_area_id()
        player = PlayerClient(self._client)

        try:
            characters = await player.fetch_characters(cookie, area_id)
        except Exception as exc:
            logger.warning(f"NIKKE 角色列表查询失败：{exc}")
            raise CharacterQueryError(f"角色列表查询失败：{exc}")

        char_info = next(
            (c for c in characters if c.get("name_code") == name_code), None
        )
        if not char_info:
            raise CharacterQueryError(f"未在账号中找到角色「{en_name}」。")

        try:
            details, effects = await player.fetch_character_details(
                cookie, area_id, [name_code]
            )
        except Exception as exc:
            logger.warning(f"NIKKE 角色详情查询失败：{exc}")
            raise CharacterQueryError(f"角色详情查询失败：{exc}")

        if not details:
            raise CharacterQueryError("角色详情数据为空。")

        return MessageBuilder.format_character_stats(
            char_info, details[0], {"en": en_name}, effects
        )
