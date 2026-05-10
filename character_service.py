from typing import Any

import httpx
from astrbot.api import logger

from character_map import CharacterMap
from config import PluginConfig
from message_builder import MessageBuilder
from player_mapping_cache import PlayerMappingCache
from player_mapping_refresher import PlayerMappingRefreshError, refresh_player_mappings
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
        mapping_cache: PlayerMappingCache | None = None,
    ):
        self._client = client
        self._character_map = character_map
        self._config = config
        self._mapping_cache = mapping_cache

    async def refresh_mappings(self) -> str:
        if not self._mapping_cache:
            return "玩家映射缓存未初始化。"

        language = self._config.player_mapping_language()
        try:
            characters, options, sources = await refresh_player_mappings(
                cookie_header=self._config.player_data_cookie(),
                language=language,
            )
        except PlayerMappingRefreshError as exc:
            return str(exc)

        if characters:
            self._character_map.update(characters)
            self._character_map.save()
        self._mapping_cache.save(
            language=language,
            characters=characters or self._character_map.snapshot(),
            state_effect_options=options,
            sources=sources,
        )
        self._mapping_cache.load()
        return f"玩家映射已刷新：{self._mapping_cache.summary()}。"

    async def query(self, name: str) -> str:
        cookie = self._config.player_data_cookie()
        if not cookie:
            raise CharacterQueryError(
                "未配置玩家 Cookie，无法查询角色数据。"
                "请先在插件配置中设置 player_reminder.cookie。"
            )

        await self._ensure_mapping_cache()

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
        language = self._config.player_mapping_language()
        game_id = self._config.player_game_id()
        player = PlayerClient(self._client)

        try:
            characters = await player.fetch_characters(
                cookie, area_id, language=language, game_id=game_id
            )
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
                cookie,
                area_id,
                [name_code],
                intl_open_id=self._config.player_open_id(),
                language=language,
                game_id=game_id,
            )
        except Exception as exc:
            logger.warning(f"NIKKE 角色详情查询失败：{exc}")
            raise CharacterQueryError(f"角色详情查询失败：{exc}")

        if not details:
            raise CharacterQueryError("角色详情数据为空。")

        return MessageBuilder.format_character_stats(
            char_info,
            details[0],
            {"en": en_name},
            effects,
            self._mapping_cache.state_effect_options if self._mapping_cache else {},
        )

    async def _ensure_mapping_cache(self) -> None:
        if not self._mapping_cache:
            return

        language = self._config.player_mapping_language()
        self._mapping_cache.load()
        if self._mapping_cache.characters:
            self._character_map.update(self._mapping_cache.characters)

        should_refresh = (
            self._config.player_auto_refresh_mapping()
            and (
                not self._mapping_cache.has_useful_data(language)
                or self._mapping_cache.is_stale(
                    self._config.player_mapping_cache_ttl_hours()
                )
            )
        )
        if not should_refresh:
            return

        msg = await self.refresh_mappings()
        if not self._mapping_cache.has_useful_data(language):
            raise CharacterQueryError(f"{msg}\n请稍后重试或执行 /nikke refresh。")
