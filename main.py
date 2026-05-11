import asyncio
import os
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx
from astrbot.api import AstrBotConfig, logger
import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from core.config import PluginConfig
from core.constants import PLUGIN_NAME, REQUEST_TIMEOUT_SECONDS
from core.poll_coordinator import PollCoordinator
from core.state_store import PluginStateStore
from news.news_poller import NewsPoller
from player.character_service import CharacterQueryError, CharacterService
from player.player_mapping_cache import PlayerMappingCache
from player.player_poller import PlayerPoller
from player.portrait_service import PortraitService


@register(
    PLUGIN_NAME,
    "monster1389",
    "轮询 Blablalink NIKKE 官方消息，并支持玩家角色查询。",
    "v1.4.0",
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
            logger.info("NIKKE 角色映射为空，请执行 /nikke refresh 刷新角色列表。")

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
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        if self._client:
            await self._client.aclose()
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
        await self._coordinator._poll_once()

    async def _seed_portraits(self, cookie: str):
        logger.info("NIKKE 开始初始头像缓存（前 30 个角色）...")
        msg = await self._portrait_service.refresh_first_n(30, cookie)
        logger.info(f"NIKKE {msg}")

    @filter.command("nikke")
    async def cmd_nikke(self, event: AstrMessageEvent, text: str = ""):
        """查询 NIKKE 角色数据。用法: /nikke <角色名>"""
        # AstrBot splits command args by spaces and maps one word per
        # parameter, so multi-word queries like "rapi rh" get truncated
        # to just "rapi" in `text`. Recover the full query from the raw
        # message (wake prefix already stripped, e.g. "nikke rapi rh").
        msg = event.message_str.strip()
        for prefix in ("/nikke ", "nikke "):
            if msg.startswith(prefix):
                text = msg[len(prefix):]
                break

        if not text or not text.strip():
            yield event.plain_result("请提供角色名，例如：/nikke anis")
            return

        if text.strip().lower() == "refresh":
            async for result in self.cmd_nikke_refresh(event):
                yield result
            return

        if text.strip().lower() in ("portrait_refresh", "refresh_portrait",
                                     "portrait refresh", "refresh portrait"):
            async for result in self.cmd_nikke_portrait_refresh(event):
                yield result
            return

        try:
            result_text, name_code = await self._character_service.query(text)

            if self._plugin_config.show_character_portrait() and self._portrait_service:
                path = self._portrait_service.portrait_path(name_code)
                if path.exists():
                    chain = [
                        Comp.Image.fromFileSystem(str(path)),
                        Comp.Plain(result_text),
                    ]
                    yield event.chain_result(chain)
                    return
                yield event.plain_result(
                    result_text
                    + "\n\n（未找到角色头像，请执行 /nikke portrait_refresh 下载头像缓存。）"
                )
                return

            yield event.plain_result(result_text)
        except CharacterQueryError as exc:
            yield event.plain_result(exc.message)

    @filter.command("nikke_refresh")
    async def cmd_nikke_refresh(self, event: AstrMessageEvent):
        """刷新 NIKKE 角色列表，并执行玩家映射刷新。"""
        if not self._character_service:
            yield event.plain_result("角色服务模块未初始化。")
            return

        messages: list[str] = []
        self._character_service._load_caches()
        count = self._character_service.count()
        messages.append(
            f"已重载本地角色列表，共 {count} 个角色。"
            if count
            else "本地角色列表加载失败，请执行 /nikke refresh 刷新。"
        )

        messages.append(await self._character_service.refresh_mappings())

        yield event.plain_result("\n".join(messages))

    async def cmd_nikke_portrait_refresh(self, event: AstrMessageEvent):
        """刷新所有角色头像缓存。"""
        if not self._portrait_service:
            yield event.plain_result("头像服务未初始化。")
            return
        cookie = self._plugin_config.player_data_cookie()
        if not cookie:
            yield event.plain_result(
                "未配置玩家 Cookie，无法获取角色头像。"
                "请先在插件配置中设置 player_reminder.cookie。"
            )
            return
        yield event.plain_result("正在抓取角色头像列表并下载...")
        msg = await self._portrait_service.refresh_all(cookie)
        yield event.plain_result(msg)


