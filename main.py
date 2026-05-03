import asyncio
import html
import json
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import MessageChain
from astrbot.api.star import Context, Star, StarTools, register


PLUGIN_NAME = "astrbot_plugin_nikke_news"
OFFICIAL_PLATE_ID = 43
POST_LIST_URL = (
    "https://api.blablalink.com/api/ugc/direct/standalonesite/"
    "Dynamics/GetPostList"
)
POST_DETAIL_URL = "https://www.blablalink.com/post/detail?post_uuid={post_uuid}"
MAX_SEEN_POSTS = 500
SUMMARY_MAX_LENGTH = 300
REQUEST_TIMEOUT_SECONDS = 60


@register(
    PLUGIN_NAME,
    "monster1389",
    "轮询 Blablalink NIKKE 官方消息并通过 NapCat QQ 主动推送。",
    "1.0.0",
)
class NikkeNewsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self._client: httpx.AsyncClient | None = None
        self._task: asyncio.Task | None = None
        self._state_path: Path | None = None
        self._state: dict[str, Any] = {
            "initialized": False,
            "seen_post_uuids": [],
        }

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
            logger.info(
                f"NIKKE 首次初始化完成，已记录 {len(fetched_uuids)} 条历史消息。",
            )
            return

        new_posts = [post for post in posts if post.get("post_uuid") not in seen]
        if not new_posts:
            logger.info(f"NIKKE 轮询完成，无新帖（已跟踪 {len(seen)} 条）。")
            return

        new_posts.sort(key=lambda post: self._safe_int(post.get("created_on")))
        logger.info(
            "NIKKE 发现新帖："
            + ", ".join(
                f"{post.get('post_uuid')[:8]}…({self._clean_text(post.get('title'))[:30]})"
                for post in new_posts
            ),
        )
        targets = self._enabled_targets()

        if not targets:
            self._mark_seen([post["post_uuid"] for post in new_posts])
            self._save_state()
            logger.warning("NIKKE 发现新帖，但未配置推送目标。")
            return

        for idx, post in enumerate(new_posts):
            post_uuid = post.get("post_uuid")
            message = self._format_post_message(post)
            delivered = False

            for target in targets:
                try:
                    await StarTools.send_message_by_id(
                        target["target_type"],
                        target["target_id"],
                        MessageChain().message(message),
                        platform="aiocqhttp",
                    )
                    delivered = True
                    logger.info(
                        f"NIKKE 消息已发送：target={target['target_type']}:{target['target_id']} "
                        f"uuid={post_uuid}"
                    )
                except Exception as exc:
                    logger.warning(
                        f"NIKKE 消息发送失败：target={target['target_type']}:{target['target_id']} "
                        f"error={exc}"
                    )

            if delivered and post_uuid:
                self._mark_seen([post_uuid])
                self._save_state()

            delay = self._push_delay_seconds()
            if delay > 0 and idx < len(new_posts) - 1:
                await asyncio.sleep(delay)

    async def _fetch_official_posts(self) -> list[dict[str, Any]]:
        if not self._client:
            return []

        payload = {
            "page": 1,
            "page_size": self._fetch_limit(),
            "plate_id": OFFICIAL_PLATE_ID,
            "area_id": "global",
            "lang": self._language(),
        }
        resp = await self._client.post(POST_LIST_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"Blablalink API 返回错误：{data}")

        items = data.get("data", {}).get("list", [])
        if not isinstance(items, list):
            raise RuntimeError(f"Blablalink API 结构异常：{data}")

        return [
            item
            for item in items
            if isinstance(item, dict)
            and self._safe_int(item.get("plate_id")) == OFFICIAL_PLATE_ID
            and self._safe_int(item.get("is_official")) == 1
            and item.get("post_uuid")
        ]

    def _format_post_message(self, post: dict[str, Any]) -> str:
        title = self._clean_text(post.get("title")) or "NIKKE 官方消息"
        summary = self._clean_text(post.get("content_summary"))
        if len(summary) > SUMMARY_MAX_LENGTH:
            summary = summary[:SUMMARY_MAX_LENGTH].rstrip() + "..."

        created_on = self._format_timestamp(post.get("created_on"))
        detail_url = POST_DETAIL_URL.format(post_uuid=post.get("post_uuid"))

        parts = [title]
        if summary:
            parts.append(summary)
        parts.append(f"发布时间：{created_on}")
        parts.append(f"链接：{detail_url}")
        return "\n\n".join(parts)

    def _enabled_targets(self) -> list[dict[str, str]]:
        enabled: list[dict[str, str]] = []
        group_targets = self.config.get("scheduled_push_groups", []) or []

        for item in group_targets:
            item_str = str(item or "").strip()
            if not item_str:
                continue

            parsed = self._parse_push_target(item_str)
            if not parsed:
                logger.warning(f"NIKKE 跳过无效推送目标：{item_str}")
                continue
            enabled.append(parsed)

        if enabled:
            return enabled

        legacy_targets = self.config.get("targets", []) or []
        for target in legacy_targets:
            if not isinstance(target, dict) or not target.get("enabled", True):
                continue

            target_type = str(target.get("target_type", "")).strip()
            target_id = str(target.get("target_id", "")).strip()
            if target_type not in {"GroupMessage", "PrivateMessage", "FriendMessage"} or not target_id:
                logger.warning(f"NIKKE 跳过无效旧版推送目标：{target}")
                continue

            enabled.append({"target_type": target_type, "target_id": target_id})

        return enabled

    @staticmethod
    def _parse_push_target(value: str) -> dict[str, str] | None:
        if value.isdigit():
            return {"target_type": "GroupMessage", "target_id": value}

        # unified_msg_origin, e.g. napcat:FriendMessage:2854964693
        parts = value.split(":")
        if len(parts) == 3 and parts[2].isdigit():
            msg_type = parts[1]
            if msg_type in {"GroupMessage", "PrivateMessage", "FriendMessage"}:
                return {"target_type": msg_type, "target_id": parts[2]}

        return None

    def _load_state(self) -> dict[str, Any]:
        if not self._state_path or not self._state_path.exists():
            return {"initialized": False, "seen_post_uuids": []}

        try:
            with self._state_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("state root is not object")
            seen = data.get("seen_post_uuids", [])
            if not isinstance(seen, list):
                seen = []
            return {
                "initialized": bool(data.get("initialized", False)),
                "seen_post_uuids": [str(item) for item in seen if item],
            }
        except Exception as exc:
            logger.warning(f"NIKKE 状态文件读取失败，将重新初始化：{exc}")
            return {"initialized": False, "seen_post_uuids": []}

    def _save_state(self):
        if not self._state_path:
            return

        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            with self._state_path.open("w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning(f"NIKKE 状态文件保存失败：{exc}")

    def _mark_seen(self, post_uuids: list[str]):
        current = [str(item) for item in self._state.get("seen_post_uuids", []) if item]
        for post_uuid in post_uuids:
            post_uuid = str(post_uuid)
            if post_uuid in current:
                current.remove(post_uuid)
            current.append(post_uuid)
        self._state["seen_post_uuids"] = current[-MAX_SEEN_POSTS:]

    def _poll_interval_seconds(self) -> int:
        return max(60, self._config_int("poll_interval_seconds", 300))

    def _fetch_limit(self) -> int:
        return min(50, max(1, self._config_int("fetch_limit", 10)))

    def _language(self) -> str:
        language = str(self.config.get("language", "zh-TW")).strip() or "zh-TW"
        if language not in {"zh-TW", "en", "ja", "ko", "zh"}:
            logger.warning(f"NIKKE 语言配置无效，已使用 zh-TW：{language}")
            return "zh-TW"
        return language

    def _config_bool(self, key: str, default: bool) -> bool:
        value = self.config.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _config_int(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default))
        except (TypeError, ValueError):
            logger.warning(f"NIKKE 配置 {key} 非法，已使用默认值 {default}。")
            return default

    def _push_delay_seconds(self) -> int:
        return min(30, max(0, self._config_int("push_delay_seconds", 2)))

    @staticmethod
    def _clean_text(value: Any) -> str:
        text = html.unescape(str(value or ""))
        return " ".join(text.split())

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _format_timestamp(cls, value: Any) -> str:
        timestamp = cls._safe_int(value)
        if timestamp <= 0:
            return "未知"
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
