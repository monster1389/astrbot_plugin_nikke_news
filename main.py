"""NIKKE 插件入口：注册命令、初始化服务、启动轮询。"""

# ruff: noqa: E402 (sys.path patching before local imports)

import asyncio
import os
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from core.config import PluginConfig
from core.constants import PLUGIN_NAME, REQUEST_TIMEOUT_SECONDS
from core.nikke_commands import (
    handle_help,
    handle_avatar_refresh_all,
    handle_query,
    handle_refresh,
    handle_skill,
)
from core.cache_refresher import CacheRefresher
from core.poll_coordinator import PollCoordinator
from core.state_store import PluginStateStore
from news.news_poller import NewsPoller
from player.character_service import CharacterService
from player.player_mapping_cache import PlayerMappingCache
from player.player_poller import PlayerPoller
from player.avatar_service import AvatarService
from player.skill_service import SkillService


@register(
    PLUGIN_NAME,
    "monster1389",
    "Blablalink官方消息推送、日常/收菜提醒、角色查询。",
    "v1.7.0",
)
class NikkeNewsPlugin(Star):
    """NIKKE 官方消息推送、玩家状态提醒、角色查询插件。

    Attributes:
        config: AstrBot 原始配置字典。
        _plugin_config: 类型化配置封装。
        _client: httpx AsyncClient 实例。
        _news_poller: 新闻轮询器。
        _player_poller: 玩家状态轮询器。
        _character_service: 角色查询服务。
        _avatar_service: 头像管理服务。
        _coordinator: 轮询调度器。
        _task: 后台轮询 asyncio Task。
        _state_path: state.json 文件路径。
        _state: 插件状态 dict。
    """

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self._plugin_config = PluginConfig(self.config)
        self._client: httpx.AsyncClient | None = None
        self._news_poller: NewsPoller | None = None
        self._player_poller: PlayerPoller | None = None
        self._character_service: CharacterService | None = None
        self._avatar_service: AvatarService | None = None
        self._skill_service: SkillService | None = None
        self._cache_refresher: CacheRefresher | None = None
        self._coordinator: PollCoordinator | None = None
        self._task: asyncio.Task | None = None
        self._state_path: Path | None = None
        self._state: dict[str, Any] = PluginStateStore.default_state()

    async def initialize(self):
        """初始化数据目录、HTTP 客户端、各服务模块，启动后台轮询。

        插件被禁用时（enabled=false）直接返回，不执行任何初始化。
        """
        if not self._config_bool("enabled", True):
            logger.info("NIKKE 官方消息推送插件已禁用。")
            return

        data_dir = StarTools.get_data_dir(PLUGIN_NAME)
        self._state_path = data_dir / "state.json"
        en_cache = PlayerMappingCache(data_dir / "player_mappings_en.json")
        mapping_lang = self._plugin_config.player_mapping_language()
        target_cache = (
            PlayerMappingCache(data_dir / f"player_mappings_{mapping_lang}.json")
            if mapping_lang != "en"
            else None
        )
        self._state = self._load_state()
        self._client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 AstrBot NIKKE News Plugin "
                    "(https://www.blablalink.com/)"
                ),
            },
        )
        self._character_service = CharacterService(
            self._client, self._plugin_config, en_cache, target_cache
        )
        self._character_service.load_caches()
        if not self._character_service.is_loaded:
            logger.info("NIKKE 角色映射为空，请执行 /nikke_refresh 刷新角色列表。")

        self._avatar_service = AvatarService(
            data_dir, self._client, self._plugin_config.player_mapping_cache_ttl_hours()
        )

        self._skill_service = SkillService(
            data_dir,
            self._client,
            self._plugin_config,
            en_cache,
            self._plugin_config.player_mapping_cache_ttl_hours(),
        )

        self._news_poller = NewsPoller(
            self._client,
            self._plugin_config,
            self._state,
            self._save_state,
            self._mark_seen,
        )
        self._player_poller = PlayerPoller(
            self._client,
            self._plugin_config,
            self._state,
            self._save_state,
        )
        self._cache_refresher = CacheRefresher(
            self._character_service,
            self._avatar_service,
            self._player_poller,
            self._plugin_config,
        )
        self._coordinator = PollCoordinator(
            news_poller=self._news_poller,
            player_poller=self._player_poller,
            state=self._state,
            state_path=self._state_path,
            poll_interval_seconds=self._poll_interval_seconds(),
            cache_refresher=self._cache_refresher,
        )
        self._task = asyncio.create_task(
            self._coordinator.run(), name=f"{PLUGIN_NAME}_poll"
        )
        logger.info("NIKKE 官方消息推送插件已启动。")

    async def terminate(self):
        """取消后台轮询任务，关闭 HTTP 客户端，保存状态。

        取消和清理操作各自容错，确保所有资源都被释放。
        """
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        if self._client:
            try:
                await self._client.aclose()
            except Exception as exc:
                logger.warning(f"NIKKE httpx client aclose 异常：{exc}", exc_info=True)
            self._client = None

        self._save_state()
        logger.info("NIKKE 官方消息推送插件已停止。")

    def _load_state(self) -> dict[str, Any]:
        return PluginStateStore(self._state_path).load()

    def _save_state(self):
        PluginStateStore(self._state_path).save(self._state)

    def _mark_seen(self, post_uuids: list[str]):
        PluginStateStore.mark_seen(self._state, post_uuids)

    def _poll_interval_seconds(self) -> int:
        return self._plugin_config.poll_interval_seconds()

    def _config_bool(self, key: str, default: bool) -> bool:
        return self._plugin_config.config_bool(key, default)

    async def _poll_once(self):
        """测试钩子：手动触发一次轮询。"""
        if self._coordinator:
            await self._coordinator._poll_once()

    @filter.command("nikke")
    async def cmd_nikke(self, event: AstrMessageEvent, text: str = ""):
        """查询 NIKKE 角色数据：/nikke <角色名>

        Args:
            event: AstrBot 消息事件。
            text: 命令行参数文本。

        Yields:
            AstrBot plain_result 或 chain_result 消息（含头像图片）。
        """
        async for result in handle_query(self, event, text):
            yield result

    @filter.command("nikke_refresh")
    async def cmd_nikke_refresh(self, event: AstrMessageEvent, text: str = ""):
        """刷新角色映射和已缓存头像：/nikke_refresh

        Args:
            event: AstrBot 消息事件。
            text: 命令行参数文本。

        Yields:
            AstrBot plain_result 消息（含分步耗时）。
        """
        async for result in handle_refresh(self, event, text):
            yield result

    @filter.command("nikke_avatar_all")
    async def cmd_nikke_avatar_all(self, event: AstrMessageEvent):
        """刷新头像映射并下载全部头像：/nikke_avatar_all

        Args:
            event: AstrBot 消息事件。

        Yields:
            AstrBot plain_result 消息。
        """
        async for result in handle_avatar_refresh_all(self, event):
            yield result

    @filter.command("nikke_skill")
    async def cmd_nikke_skill(self, event: AstrMessageEvent, text: str = ""):
        """查询角色技能详细描述：/nikke_skill <角色名>

        Args:
            event: AstrBot 消息事件。
            text: 命令行参数文本。

        Yields:
            AstrBot plain_result 消息。
        """
        async for result in handle_skill(self, event, text):
            yield result

    @filter.command("nikke_help")
    async def cmd_nikke_help(self, event: AstrMessageEvent):
        """显示 NIKKE 插件帮助：/nikke_help"""
        yield event.plain_result(handle_help())
