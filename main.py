import asyncio
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

# AstrBot may import plugin entrypoints without adding the plugin folder to sys.path.
# Ensure sibling modules (config.py, state_store.py, etc.) are importable.
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from character_service import CharacterQueryError, CharacterService
from config import PluginConfig
from constants import PLUGIN_NAME, REQUEST_TIMEOUT_SECONDS
from news_poller import NewsPoller
from player_mapping_cache import PlayerMappingCache
from player_poller import PlayerPoller
from state_store import PluginStateStore


@register(
    PLUGIN_NAME,
    "monster1389",
    "轮询 Blablalink NIKKE 官方消息，并支持玩家角色查询。",
    "v1.3.0",
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
        self._mapping_cache: PlayerMappingCache | None = None
        self._task: asyncio.Task | None = None
        self._state_path: Path | None = None
        self._state: dict[str, Any] = PluginStateStore.default_state()

    async def initialize(self):
        if not self._config_bool("enabled", True):
            logger.info("NIKKE 官方消息推送插件已禁用。")
            return

        data_dir = StarTools.get_data_dir(PLUGIN_NAME)
        self._state_path = data_dir / "state.json"
        self._mapping_cache = PlayerMappingCache(data_dir / "player_mappings.json")
        self._mapping_cache.load()
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
            self._client, self._plugin_config, self._mapping_cache
        )
        if self._mapping_cache.characters:
            self._character_service.update_characters(self._mapping_cache.characters)
        else:
            logger.info("NIKKE 角色映射为空，请执行 /nikke refresh 刷新角色列表。")

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
        self._task = asyncio.create_task(self._poll_loop(), name=f"{PLUGIN_NAME}_poll")
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

    async def _poll_loop(self):
        logger.info("NIKKE 轮询循环已开始。")
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    f"NIKKE 轮询异常（{type(exc).__name__}），将在下次重试：{exc}"
                )

            await asyncio.sleep(self._poll_interval_seconds())

    async def _poll_once(self):
        self._state = self._load_state()
        await self._news_poller.poll()
        try:
            await self._player_poller.poll()
        except Exception as exc:
            logger.warning(f"NIKKE 玩家数据轮询异常，将在下次重试：{exc}")

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

        try:
            result = await self._character_service.query(text)
            yield event.plain_result(result)
        except CharacterQueryError as exc:
            yield event.plain_result(exc.message)

    @filter.command("nikke_refresh")
    async def cmd_nikke_refresh(self, event: AstrMessageEvent):
        """刷新 NIKKE 角色列表。若配置了 character_list_url 则从 CDN 拉取，否则重载本地缓存数据。"""
        if not self._character_service:
            yield event.plain_result("角色服务模块未初始化。")
            return

        messages: list[str] = []
        url = self._plugin_config.character_list_url()
        if url:
            msg, chars = await self._character_service.refresh_from_url(url)
            messages.append(msg)
            if chars and self._mapping_cache:
                self._mapping_cache.save(
                    language=self._plugin_config.player_mapping_language(),
                    characters=chars,
                    state_effect_options=self._mapping_cache.state_effect_options,
                    sources={},
                )
        else:
            self._mapping_cache.load()
            if self._mapping_cache.characters:
                self._character_service.update_characters(self._mapping_cache.characters)
            count = (
                self._character_service.count()
                if self._character_service.is_loaded
                else 0
            )
            messages.append(
                f"已重载本地角色列表，共 {count} 个角色。"
                if count
                else "本地角色列表加载失败，请执行 /nikke refresh 刷新。"
            )

        if self._character_service:
            messages.append(await self._character_service.refresh_mappings())

        yield event.plain_result("\n".join(messages))


