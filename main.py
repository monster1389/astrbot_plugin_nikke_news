import asyncio
import sys
from contextlib import suppress
from datetime import datetime
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

from character_map import CharacterMap
from character_service import CharacterQueryError, CharacterService
from config import PluginConfig
from constants import PLUGIN_NAME, REQUEST_TIMEOUT_SECONDS
from message_builder import MessageBuilder
from news_poller import NewsPoller
from player_poller import PlayerPoller
from state_store import PluginStateStore
from targets import enabled_targets, parse_push_target
from time_utils import day_key, is_cookie_invalid_error
from utils import (
    clean_html_with_linebreaks,
    clean_text,
    format_timestamp,
    is_video_post,
    safe_float,
    safe_int,
)


@register(
    PLUGIN_NAME,
    "monster1389",
    "轮询 Blablalink NIKKE 官方消息并通过 NapCat QQ 主动推送。",
    "v1.2.0",
)
class NikkeNewsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self._plugin_config = PluginConfig(self.config)
        self._client: httpx.AsyncClient | None = None
        self._news_poller: NewsPoller | None = None
        self._player_poller: PlayerPoller | None = None
        self._character_map: CharacterMap | None = None
        self._character_service: CharacterService | None = None
        self._task: asyncio.Task | None = None
        self._state_path: Path | None = None
        self._state: dict[str, Any] = PluginStateStore.default_state()

    async def initialize(self):
        if not self._config_bool("enabled", True):
            logger.info("NIKKE 官方消息推送插件已禁用。")
            return

        data_dir = StarTools.get_data_dir(PLUGIN_NAME)
        self._state_path = data_dir / "state.json"
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
        self._character_map = CharacterMap(
            _PLUGIN_DIR / "character_map.json",
            self._plugin_config.character_aliases(),
        )
        if not self._character_map.load():
            logger.info("NIKKE 角色映射加载失败，请检查 character_map.json。")

        self._character_service = CharacterService(
            self._client, self._character_map, self._plugin_config
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

    # Compatibility wrapper for existing tests
    def _format_post_message(self, post: dict[str, Any]) -> str:
        return MessageBuilder(self._plugin_config).format_post_message(post)

    def _load_state(self) -> dict[str, Any]:
        return PluginStateStore(self._state_path).load()

    def _save_state(self):
        PluginStateStore(self._state_path).save(self._state)

    def _mark_seen(self, post_uuids: list[str]):
        PluginStateStore.mark_seen(self._state, post_uuids)

    def _enabled_targets(self) -> list[dict[str, str]]:
        return enabled_targets(self._plugin_config.news_config())

    @staticmethod
    def _parse_push_target(value: str) -> dict[str, str] | None:
        return parse_push_target(value)

    def _poll_interval_seconds(self) -> int:
        return self._plugin_config.poll_interval_seconds()

    def _fetch_limit(self) -> int:
        return self._plugin_config.fetch_limit()

    def _language(self) -> str:
        return self._plugin_config.language()

    def _config_bool(self, key: str, default: bool) -> bool:
        return self._plugin_config.config_bool(key, default)

    def _config_int(self, key: str, default: int) -> int:
        return self._plugin_config.config_int(key, default)

    def _push_delay_seconds(self) -> int:
        return self._plugin_config.push_delay_seconds()

    def _push_prefix(self) -> str:
        return self._plugin_config.push_prefix()

    def _content_mode(self) -> str:
        return self._plugin_config.content_mode()

    def _max_images(self) -> int:
        return self._plugin_config.max_images()

    def _show_publish_time(self) -> bool:
        return self._plugin_config.show_publish_time()

    @staticmethod
    def _is_video_post(post: dict[str, Any]) -> bool:
        return is_video_post(post)

    @staticmethod
    def _clean_text(value: Any) -> str:
        return clean_text(value)

    @staticmethod
    def _clean_html_with_linebreaks(value: Any) -> str:
        return clean_html_with_linebreaks(value)

    @staticmethod
    def _safe_int(value: Any) -> int:
        return safe_int(value)

    @staticmethod
    def _safe_float(value: Any) -> float:
        return safe_float(value)

    @classmethod
    def _format_timestamp(cls, value: Any) -> str:
        return format_timestamp(value)

    @staticmethod
    def _is_cookie_invalid_error(exc: Exception) -> bool:
        return is_cookie_invalid_error(exc)

    @staticmethod
    def _day_key(now: datetime) -> str:
        return day_key(now)

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
        """刷新 NIKKE 角色列表。若配置了 character_list_url 则从 CDN 拉取，否则重载本地打包数据。"""
        if not self._character_map:
            yield event.plain_result("角色映射模块未初始化。")
            return

        url = self._plugin_config.character_list_url()
        if url:
            msg = await self._character_map.refresh(self._client, url)
        else:
            self._character_map.load()
            count = (
                len(self._character_map._name_to_code)
                if self._character_map.is_loaded
                else 0
            )
            msg = (
                f"已重载本地角色列表，共 {count} 个角色。"
                if count
                else "本地角色列表加载失败，请检查 character_map.json。"
            )
        yield event.plain_result(msg)


