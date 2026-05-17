from typing import Any

import httpx
from astrbot.api import logger

from core.config import PluginConfig
from player.character_formatter import format_character_stats
from player.player_mapping_cache import PlayerMappingCache
from player.player_mapping_refresher import (
    PlayerMappingRefreshError,
    refresh_player_mappings,
)
from player.player_client import PlayerClient


class CharacterQueryError(Exception):
    """角色查询错误，包含面向用户的中文消息。"""

    def __init__(self, message: str):
        self.message = message


class CharacterService:
    """玩家角色查询：别名查找、API 数据获取、映射刷新。"""

    def __init__(
        self,
        client: httpx.AsyncClient,
        config: PluginConfig,
        en_cache: PlayerMappingCache | None = None,
        target_cache: PlayerMappingCache | None = None,
    ):
        self._client = client
        self._config = config
        self._en_cache = en_cache
        self._target_cache = target_cache
        self._name_to_code: dict[str, int] = {}
        self._code_to_name: dict[int, str] = {}
        self._state_effect_options: dict[str, dict[str, Any]] = {}
        self._aliases: dict[str, list[str]] = config.character_aliases()

    @property
    def is_loaded(self) -> bool:
        return len(self._name_to_code) > 0

    def count(self) -> int:
        return len(self._name_to_code)

    def is_mapping_stale(self) -> bool:
        """任一映射缓存（en 或目标语言）过期或无效时返回 True。"""
        ttl = self._config.player_mapping_cache_ttl_hours()
        if not self._en_cache or not self._en_cache.has_useful_data() or self._en_cache.is_stale(ttl):
            return True
        target_lang = self._config.player_mapping_language()
        if target_lang != "en" and self._target_cache:
            if not self._target_cache.has_useful_data() or self._target_cache.is_stale(ttl):
                return True
        return False

    def _load_caches(self) -> None:
        if not self._en_cache:
            return

        self._en_cache.load()
        self._name_to_code = self._en_cache.name_to_code()
        self._state_effect_options = dict(self._en_cache.state_effect_options)

        language = self._config.player_mapping_language()
        if language != "en" and self._target_cache:
            self._target_cache.load()
            self._code_to_name = dict(self._target_cache.character_names)
            target_options = self._target_cache.state_effect_options
            if target_options:
                self._state_effect_options.update(target_options)
        else:
            self._code_to_name = {}

    def _build_alias_map(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for en_name, alias_list in self._aliases.items():
            for alias in alias_list:
                key = alias.strip().lower()
                if key and key not in result:
                    result[key] = en_name
        return result

    def _display_name(self, code: int, fallback: str) -> str:
        return self._code_to_name.get(code) or fallback

    def lookup(self, query: str) -> list[tuple[int, str]]:
        """多阶段角色查找：别名精确匹配→中英文字段精确匹配→子串匹配。"""
        if not query or not query.strip():
            return []

        q = query.strip().lower()
        alias_map = self._build_alias_map()

        alias_name = alias_map.get(q)
        if alias_name and alias_name in self._name_to_code:
            code = self._name_to_code[alias_name]
            return [(code, self._display_name(code, alias_name))]

        for name, code in self._name_to_code.items():
            if name.lower() == q:
                return [(code, self._display_name(code, name))]

        for code, display_name in self._code_to_name.items():
            if display_name.lower() == q:
                return [(code, display_name)]

        results: list[tuple[int, str]] = []
        seen: set[int] = set()

        for name, code in self._name_to_code.items():
            if q in name.lower():
                results.append((code, self._display_name(code, name)))
                seen.add(code)

        for code, display_name in self._code_to_name.items():
            if code not in seen and q in display_name.lower():
                results.append((code, display_name))

        return results

    async def refresh_mappings(self, *, force: bool = False) -> str:
        """启动 Playwright 刷新角色映射（先 en 后目标语言）。

        Args:
            force: True 时跳过 TTL 检查，强制刷新所有缓存。
        """
        if not self._en_cache:
            return "玩家映射缓存未初始化。"

        cookie = self._config.player_data_cookie()
        target_lang = self._config.player_mapping_language()
        ttl = self._config.player_mapping_cache_ttl_hours()
        messages: list[str] = []

        # Always refresh en first
        if force or not self._en_cache.has_useful_data() or self._en_cache.is_stale(ttl):
            try:
                names, options, sources = await refresh_player_mappings(
                    cookie_header=cookie,
                    language="en",
                )
            except PlayerMappingRefreshError as exc:
                messages.append(str(exc))
            else:
                self._en_cache.save(
                    language="en",
                    character_names=names,
                    state_effect_options=options,
                    sources=sources,
                )
                messages.append(
                    f"英文映射已刷新：角色 {len(names)} 个，词条 {len(options)} 个。"
                )

        # Refresh target language if different from en
        if target_lang != "en" and self._target_cache:
            if (
                force
                or not self._target_cache.has_useful_data()
                or self._target_cache.is_stale(ttl)
            ):
                try:
                    names, options, sources = await refresh_player_mappings(
                        cookie_header=cookie,
                        language=target_lang,
                    )
                except PlayerMappingRefreshError as exc:
                    messages.append(str(exc))
                else:
                    self._target_cache.save(
                        language=target_lang,
                        character_names=names,
                        state_effect_options=options,
                        sources=sources,
                    )
                    messages.append(
                        f"{target_lang} 映射已刷新：角色 {len(names)} 个，词条 {len(options)} 个。"
                    )

        self._load_caches()
        return "\n".join(messages) if messages else "映射缓存均为最新，无需刷新。"

    async def query(self, name: str) -> tuple[str, int]:
        """处理 /nikke 查询：参数校验→映射准备→Lookup→API 调用→格式化结果。"""
        cookie = self._config.player_data_cookie()
        if not cookie:
            raise CharacterQueryError(
                "未配置玩家 Cookie，无法查询角色数据。"
                "请先在插件配置中设置玩家状态提醒的 Cookie。"
            )

        await self._ensure_mapping_cache()

        if not self.is_loaded:
            raise CharacterQueryError(
                "角色数据尚未加载，请执行 /nikke refresh 刷新角色列表。"
            )

        matches = self.lookup(name)
        if not matches:
            raise CharacterQueryError(f"未找到角色「{name}」，请检查名称是否正确。")

        if len(matches) > 1:
            names = "、".join(f"「{n}」" for _, n in matches[:10])
            hint = "\n请提供更精确的名称。" if len(matches) > 10 else ""
            raise CharacterQueryError(f"找到 {len(matches)} 个匹配：\n{names}{hint}")

        name_code, display_name = matches[0]
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
            raise CharacterQueryError(f"未在账号中找到角色「{display_name}」。")

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

        text = format_character_stats(
            char_info,
            details[0],
            {"en": display_name},
            effects,
            self._state_effect_options,
        )
        return text, name_code

    async def _ensure_mapping_cache(self) -> None:
        if not self._en_cache:
            return

        self._load_caches()

        if not self._config.player_auto_refresh_mapping() or not self.is_mapping_stale():
            return

        msg = await self.refresh_mappings()
        self._load_caches()

        target_lang = self._config.player_mapping_language()
        if not self._en_cache.has_useful_data():
            raise CharacterQueryError(f"{msg}\n请稍后重试或执行 /nikke refresh。")
        if (
            target_lang != "en"
            and self._target_cache
            and not self._target_cache.has_useful_data()
        ):
            raise CharacterQueryError(f"{msg}\n请稍后重试或执行 /nikke refresh。")
