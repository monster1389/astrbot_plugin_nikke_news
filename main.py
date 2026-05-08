import asyncio
import sys
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import MessageChain
from astrbot.api.star import Context, Star, StarTools, register

# AstrBot may import plugin entrypoints without adding the plugin folder to sys.path.
# Ensure sibling modules (config.py, state_store.py, etc.) are importable.
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from config import PluginConfig
from constants import CST, PLUGIN_NAME, REQUEST_TIMEOUT_SECONDS
from message_builder import MessageBuilder
from news_client import NewsClient
from player_client import PlayerClient
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
        await self._poll_news_once()
        try:
            await self._poll_player_once()
        except Exception as exc:
            logger.warning(f"NIKKE 玩家数据轮询异常，将在下次重试：{exc}")

    async def _poll_news_once(self):
        posts = await self._fetch_official_posts()
        if not posts:
            logger.warning("NIKKE 未获取到任何帖子（API 返回空或客户端未就绪）。")
            return

        seen = set(self._state.get("seen_post_uuids", []))
        fetched_uuids = [post["post_uuid"] for post in posts if post.get("post_uuid")]

        if not self._state.get("initialized", False):
            self._mark_seen(fetched_uuids)
            self._state["initialized"] = True
            self._save_state()
            logger.info(f"NIKKE 首次初始化完成，已记录 {len(fetched_uuids)} 条历史消息。")
            return

        new_posts = [post for post in posts if post.get("post_uuid") not in seen]
        if not new_posts:
            logger.debug(f"NIKKE 轮询完成，无新帖（已跟踪 {len(seen)} 条）。")
            return

        new_posts.sort(key=lambda post: self._safe_int(post.get("created_on")))
        logger.info(
            "NIKKE 发现新帖："
            + ", ".join(
                f"{post.get('post_uuid')[:8]}…({self._clean_text(post.get('title'))[:30]})"
                for post in new_posts
            )
        )
        targets = self._enabled_targets()

        if not targets:
            self._mark_seen([post["post_uuid"] for post in new_posts])
            self._save_state()
            logger.warning("NIKKE 发现新帖，但未配置推送目标。")
            return

        for idx, post in enumerate(new_posts):
            post_uuid = post.get("post_uuid")

            for target in targets:
                try:
                    await StarTools.send_message_by_id(
                        target["target_type"],
                        target["target_id"],
                        self._format_post_message_chain(post),
                        platform="aiocqhttp",
                    )
                    logger.info(
                        f"NIKKE 消息已发送：target={target['target_type']}:{target['target_id']} uuid={post_uuid}"
                    )
                except Exception as exc:
                    logger.warning(
                        f"NIKKE 消息发送失败：target={target['target_type']}:{target['target_id']} "
                        f"type={type(exc).__name__} error={exc or '<empty>'}"
                    )

            if post_uuid:
                self._mark_seen([post_uuid])
                self._save_state()

            delay = self._push_delay_seconds()
            if delay > 0 and idx < len(new_posts) - 1:
                await asyncio.sleep(delay)

    async def _poll_player_once(self):
        if not self._plugin_config.player_data_enabled():
            return

        cookie = self._plugin_config.player_data_cookie()
        if not cookie:
            logger.warning("NIKKE 玩家数据功能已启用，但未配置 player_reminder.cookie。")
            return

        targets = self._enabled_targets()
        if not targets:
            logger.warning("NIKKE 玩家数据功能已启用，但未配置推送目标。")
            return

        player_state = self._state.setdefault("player_alert_state", {})
        player_state.setdefault("cookie_invalid_notified", False)
        player_state.setdefault("last_outpost_alert_day_key", "")
        player_state.setdefault("last_daily_mission_alert_day_key", "")

        try:
            data = await PlayerClient(self._client).fetch_progress(cookie)
            if player_state.get("cookie_invalid_notified"):
                player_state["cookie_invalid_notified"] = False
                self._save_state()
        except Exception as exc:
            if self._is_cookie_invalid_error(exc):
                if not player_state.get("cookie_invalid_notified", False):
                    await self._send_player_alert(
                        targets,
                        [
                            "登录态已失效，请更新 player_data_cookie。",
                            "当前仅首次失效发送聊天提醒，后续将只写日志。",
                        ],
                    )
                    player_state["cookie_invalid_notified"] = True
                    self._save_state()
                logger.warning(f"NIKKE 玩家 Cookie 失效：{exc}")
                return
            raise

        now = datetime.now(CST)
        today_key = self._day_key(now)
        remind_time = self._plugin_config.player_daily_mission_remind_time()
        remind_dt = datetime.combine(now.date(), remind_time, tzinfo=CST)

        lines: list[str] = []
        save_needed = False

        threshold = self._plugin_config.outpost_fullness_threshold_percent()
        if threshold > 0:
            fullness = self._safe_float(data.get("outpost_battle_storage_fullness"))
            fullness_percent = fullness * 100
            last_day = str(player_state.get("last_outpost_alert_day_key", ""))
            if fullness_percent >= threshold and last_day != today_key:
                lines.append(
                    f"前哨基地存储 {fullness_percent:.0f}%，已达到/超过阈值 {threshold}%，建议尽快上线收菜。"
                )
                player_state["last_outpost_alert_day_key"] = today_key
                save_needed = True

        if self._plugin_config.player_remind_daily_mission_enabled():
            points = self._safe_int(data.get("daily_mission_received_points"))
            last_day = str(player_state.get("last_daily_mission_alert_day_key", ""))
            if points == 0 and now >= remind_dt and last_day != today_key:
                lines.append("今日日常任务积分仍为 0，请记得完成日常。")
                player_state["last_daily_mission_alert_day_key"] = today_key
                save_needed = True

        if lines:
            await self._send_player_alert(targets, lines)

        if save_needed:
            self._save_state()

    async def _send_player_alert(self, targets: list[dict[str, str]], lines: list[str]):
        chain = MessageChain().message(MessageBuilder(self._plugin_config).format_player_alert_message(lines))
        for target in targets:
            try:
                await StarTools.send_message_by_id(
                    target["target_type"],
                    target["target_id"],
                    chain,
                    platform="aiocqhttp",
                )
            except Exception as exc:
                logger.warning(
                    f"NIKKE 玩家提醒发送失败：target={target['target_type']}:{target['target_id']} error={exc}"
                )

    # Compatibility wrappers for existing tests/calls
    async def _fetch_official_posts(self) -> list[dict[str, Any]]:
        return await NewsClient(self._client, self._plugin_config).fetch_official_posts()

    def _format_post_message(self, post: dict[str, Any]) -> str:
        return MessageBuilder(self._plugin_config).format_post_message(post)

    def _format_post_message_chain(self, post: dict[str, Any]) -> MessageChain:
        return MessageBuilder(self._plugin_config).format_post_message_chain(post)

    def _post_image_urls(self, post: dict[str, Any]) -> list[str]:
        return MessageBuilder(self._plugin_config).post_image_urls(post)

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


