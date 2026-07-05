"""角色查询服务——模糊匹配、映射刷新、角色详情。"""

from __future__ import annotations

import asyncio
import time
from typing import Any, TYPE_CHECKING

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

if TYPE_CHECKING:
    from playwright.async_api import Browser


class CharacterQueryError(Exception):
    """角色查询错误，包含面向用户的中文消息。

    Attributes:
        message: 面向用户的中文错误描述。
    """

    def __init__(self, message: str):
        self.message = message


class CharacterService:
    """玩家角色查询：别名查找、API 数据获取、映射刷新。

    Attributes:
        _client: httpx AsyncClient 实例。
        _config: 插件配置实例。
        _en_cache: 英文角色映射缓存。
        _target_cache: 目标语言角色映射缓存（可能为 None）。
        _code_to_en_name: name_code → 英文角色名映射。
        _code_to_name: name_code → 目标语言角色名映射。
        _state_effect_options: 词条 option ID → 元数据映射。
        _aliases: 角色别名配置。
    """

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
        self._code_to_en_name: dict[int, str] = {}
        self._code_to_name: dict[int, str] = {}
        self._state_effect_options: dict[str, dict[str, Any]] = {}
        self._aliases: dict[str, list[str]] = config.character_aliases()
        self._refreshing = False

    @property
    def is_loaded(self) -> bool:
        """角色映射是否已加载（含至少一个角色）。"""
        return len(self._code_to_en_name) > 0

    def count(self) -> int:
        """返回已加载的角色数量。"""
        return len(self._code_to_en_name)

    def is_mapping_stale(self) -> bool:
        """任一映射缓存（en 或目标语言）过期或无效时返回 True。"""
        ttl = self._config.player_mapping_cache_ttl_hours()
        if (
            not self._en_cache
            or not self._en_cache.has_useful_data()
            or self._en_cache.is_stale(ttl)
        ):
            return True
        target_lang = self._config.player_mapping_language()
        if target_lang != "en" and self._target_cache:
            if not self._target_cache.has_useful_data() or self._target_cache.is_stale(
                ttl
            ):
                return True
        return False

    def load_caches(self) -> None:
        """从磁盘加载角色映射和词条选项到内存。

        en 缓存必须存在且有效；目标语言缓存仅当与 en 不同时加载。
        """
        if not self._en_cache:
            return

        self._en_cache.load()
        self._code_to_en_name = dict(self._en_cache.character_names)
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
        """多阶段角色查找。

        匹配顺序：别名精确匹配 → 英文名精确匹配 → 目标语言名精确匹配
        → 英文名子串匹配 → 目标语言名子串匹配。

        Args:
            query: 用户输入的角色名查询字符串。

        Returns:
            [(name_code, display_name), ...] 列表，无匹配返回空列表。
        """
        if not query or not query.strip():
            return []

        q = query.strip().lower()
        alias_map = self._build_alias_map()

        alias_name = alias_map.get(q)
        if alias_name:
            results: list[tuple[int, str]] = []
            for code, en_name in self._code_to_en_name.items():
                if en_name == alias_name:
                    results.append((code, self._display_name(code, en_name)))
            if results:
                return results

        results: list[tuple[int, str]] = []
        for code, en_name in self._code_to_en_name.items():
            if en_name.lower() == q:
                results.append((code, self._display_name(code, en_name)))
        if results:
            return results

        for code, display_name in self._code_to_name.items():
            if display_name.lower() == q:
                return [(code, display_name)]

        results = []
        seen: set[int] = set()

        for code, en_name in self._code_to_en_name.items():
            if q in en_name.lower():
                results.append((code, self._display_name(code, en_name)))
                seen.add(code)

        for code, display_name in self._code_to_name.items():
            if code not in seen and q in display_name.lower():
                results.append((code, display_name))

        return results

    async def refresh_mappings(
        self, *, force: bool = False, _browser: Browser | None = None
    ) -> tuple[str, bool]:
        """启动 Playwright 刷新角色映射（并行 en + 目标语言）。

        Args:
            force: True 时跳过 TTL 检查，强制刷新所有缓存。
            _browser: 可复用的 Playwright Browser 实例，None 则自动创建。

        Returns:
            (消息文本, 是否有失败) 元组。
        """
        if not self._en_cache:
            return ("玩家映射缓存未初始化。", True)

        if self._refreshing:
            return ("正在刷新中，请稍后重试。", False)
        self._refreshing = True
        try:
            t0 = time.monotonic()
            cookie = self._config.player_data_cookie()
            target_lang = self._config.player_mapping_language()
            ttl = self._config.player_mapping_cache_ttl_hours()
            messages: list[str] = []
            has_failure = False
            did_refresh = False

            async def _refresh_one(lang: str, cache, lang_label: str):
                try:
                    names, options, sources, resource_ids = await refresh_player_mappings(
                        cookie_header=cookie,
                        language=lang,
                        _browser=_browser,
                    )
                except PlayerMappingRefreshError as exc:
                    return (str(exc), True)
                else:
                    cache.save(
                        language=lang,
                        character_names=names,
                        state_effect_options=options,
                        sources=sources,
                        resource_ids=resource_ids,
                    )
                    return (
                        f"{lang_label} 映射已刷新：角色 {len(names)} 个，词条 {len(options)} 个。",
                        False,
                    )

            tasks: list[tuple[str, object]] = []
            if (
                force
                or not self._en_cache.has_useful_data()
                or self._en_cache.is_stale(ttl)
            ):
                tasks.append(("en", _refresh_one("en", self._en_cache, "英文")))
            if target_lang != "en" and self._target_cache:
                if (
                    force
                    or not self._target_cache.has_useful_data()
                    or self._target_cache.is_stale(ttl)
                ):
                    tasks.append(
                        (target_lang, _refresh_one(target_lang, self._target_cache, target_lang))
                    )

            if tasks:
                did_refresh = True
                results = await asyncio.gather(*[t[1] for t in tasks])
                for msg, failed in results:
                    if failed:
                        has_failure = True
                    messages.append(msg)

            self.load_caches()
            reload_count = self.count()
            if reload_count:
                messages.append(f"已重载本地角色列表，共 {reload_count} 个角色。")

            elapsed = time.monotonic() - t0
            if did_refresh:
                logger.info(f"NIKKE 角色映射刷新完成（{elapsed:.0f}s）")
            return ("\n".join(messages), has_failure)
        finally:
            self._refreshing = False

    async def query(self, name: str) -> tuple[str, int]:
        """处理 /nikke 查询：校验 Cookie → 确保映射 → 查找 → API 调用 → 格式化。

        Args:
            name: 用户输入的角色名。

        Returns:
            (格式化统计文本, name_code) 元组。

        Raises:
            CharacterQueryError: Cookie 未配置、角色未找到、API 调用失败等。
        """
        cookie = self._config.player_data_cookie()
        if not cookie:
            raise CharacterQueryError(
                "未配置玩家 Cookie，无法查询角色数据。"
                "请先在插件配置中设置玩家状态提醒的 Cookie。"
            )

        self.load_caches()

        if not self.is_loaded:
            raise CharacterQueryError(
                "角色数据尚未加载，请执行 /nikke_refresh 刷新角色列表。"
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
