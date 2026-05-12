import asyncio
from typing import Any, Callable

import httpx
from astrbot.api import logger
from astrbot.api.star import StarTools

from core.config import PluginConfig
from core.message_builder import MessageBuilder
from news.news_client import NewsClient
from core.targets import enabled_targets
from core.utils import clean_text, safe_int


class NewsPoller:
    def __init__(
        self,
        client: httpx.AsyncClient | None,
        config: PluginConfig,
        state: dict[str, Any],
        save_state: Callable[[], None],
        mark_seen: Callable[[list[str]], None],
    ):
        self._client = client
        self._config = config
        self._state = state
        self._save_state = save_state
        self._mark_seen = mark_seen

    async def poll(self) -> None:
        posts = await NewsClient(self._client, self._config).fetch_official_posts()
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
                f"NIKKE 首次初始化完成，已记录 {len(fetched_uuids)} 条历史消息。"
            )
            return

        new_posts = [post for post in posts if post.get("post_uuid") not in seen]
        if not new_posts:
            logger.debug(f"NIKKE 轮询完成，无新帖（已跟踪 {len(seen)} 条）。")
            return

        new_posts.sort(key=lambda post: safe_int(post.get("created_on")))
        logger.info(
            "NIKKE 发现新帖："
            + ", ".join(
                f"{post.get('post_uuid')[:8]}…({clean_text(post.get('title'))[:30]})"
                for post in new_posts
            )
        )

        targets = enabled_targets(self._config.news_config())
        if not targets:
            self._mark_seen([post["post_uuid"] for post in new_posts])
            self._save_state()
            logger.warning("NIKKE 发现新帖，但未配置推送目标。")
            return

        builder = MessageBuilder(self._config)
        for idx, post in enumerate(new_posts):
            post_uuid = post.get("post_uuid")
            chain = builder.format_post_message_chain(post)

            for target in targets:
                try:
                    await StarTools.send_message_by_id(
                        target["target_type"],
                        target["target_id"],
                        chain,
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

            delay = min(30, max(0, self._config.push_delay_seconds()))
            if delay > 0 and idx < len(new_posts) - 1:
                await asyncio.sleep(delay)
