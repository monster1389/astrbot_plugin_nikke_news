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
    handle_portrait_refresh,
    handle_query,
    handle_refresh,
)
from core.poll_coordinator import PollCoordinator
from core.state_store import PluginStateStore
from news.news_poller import NewsPoller
from player.character_service import CharacterService
from player.player_mapping_cache import PlayerMappingCache
from player.player_poller import PlayerPoller
from player.portrait_service import PortraitService


@register(
    PLUGIN_NAME,
    "monster1389",
    "Blablalink官方消息推送、日常/收菜提醒、角色查询。",
    "v1.6.2",
)
class NikkeNewsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self._plugin_config = PluginConfig(self.config)
        self._client: httpx.AsyncClient | None = None
        self._news_poller: NewsPoller | None = None
        self._player_poller: PlayerPoller | None = None
        self._character_service: CharacterService | None = None
        self._portrait_service: PortraitService | None = None
        self._en_cache: PlayerMappingCache | None = None
        self._target_cache: PlayerMappingCache | None = None
        self._coordinator: PollCoordinator | None = None
        self._task: asyncio.Task | None = None
        self._state_path: Path | None = None
        self._state: dict[str, Any] = PluginStateStore.default_state()

    async def initialize(self):
        """初始化数据目录、HTTP 客户端、各服务模块，启动后台轮询。"""
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
        en_cache.load()
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
        self._character_service._load_caches()
        if not self._character_service.is_loaded:
            logger.info("NIKKE 角色映射为空，请执行 /nikke_refresh 刷新角色列表。")

        self._portrait_service = PortraitService(data_dir, self._client)
        cached = self._portrait_service.cached_count()
        if cached == 0 and self._plugin_config.player_data_enabled():
            cookie = self._plugin_config.player_data_cookie()
            if cookie:
                asyncio.create_task(
                    self._seed_portraits(cookie),
                    name=f"{PLUGIN_NAME}_portrait_seed",
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
        self._coordinator = PollCoordinator(
            news_poller=self._news_poller,
            player_poller=self._player_poller,
            state=self._state,
            state_path=self._state_path,
            poll_interval_seconds=self._poll_interval_seconds(),
        )
        self._task = asyncio.create_task(
            self._coordinator.run(), name=f"{PLUGIN_NAME}_poll"
        )
        logger.info("NIKKE 官方消息推送插件已启动。")

    async def terminate(self):
        """取消轮询任务，关闭 HTTP 客户端，保存状态。"""
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

    async def _seed_portraits(self, cookie: str):
        """启动时预缓存前 30 个角色头像。"""
        logger.info("NIKKE 开始初始头像缓存（前 30 个角色）...")
        msg = await self._portrait_service.refresh_first_n(30, cookie)
        logger.info(f"NIKKE {msg}")

    @filter.command("nikke")
    async def cmd_nikke(self, event: AstrMessageEvent, text: str = ""):
        """查询 NIKKE 角色数据：/nikke <角色名>"""
        async for result in handle_query(self, event, text):
            yield result

    @filter.command("nikke_refresh")
    async def cmd_nikke_refresh(self, event: AstrMessageEvent):
        """刷新 NIKKE 角色映射：/nikke_refresh"""
        async for result in handle_refresh(self, event):
            yield result

    @filter.command("nikke_portrait_refresh")
    async def cmd_nikke_portrait_refresh(self, event: AstrMessageEvent):
        """下载/刷新所有角色头像：/nikke_portrait_refresh"""
        async for result in handle_portrait_refresh(self, event):
            yield result

    @filter.command("nikke_help")
    async def cmd_nikke_help(self, event: AstrMessageEvent):
        """显示 NIKKE 插件帮助：/nikke_help"""
        yield event.plain_result(handle_help())
