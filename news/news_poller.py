"""轮询官方公告新增并推送到目标群。"""

import asyncio
from typing import Any, Callable

import httpx
from astrbot.api import logger

from core.config import PluginConfig
from core.message_builder import MessageBuilder
from news.news_client import NewsClient
from core.targets import broadcast_to_targets, enabled_targets
from core.utils import clean_text, safe_int


class NewsPoller:
    """对比已见帖子 UUID，将新帖推送到配置的目标群组。

    Attributes:
        _client: httpx AsyncClient 实例。
        _config: 插件配置实例。
        _state: 插件状态 dict（共享引用）。
        _save_state: 状态保存回调。
        _mark_seen: 标记已见回调。
    """

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

    async def poll(self) -> str:
        """拉取 API → 对比 seen 集合 → 推送新帖到配置的目标群。

        首次运行时初始化 seen 集合而不推送。
        """
        posts = await NewsClient(self._client, self._config).fetch_official_posts()
        if not posts:
            logger.warning("NIKKE 未获取到任何帖子（API 返回空或客户端未就绪）。")
            return ""

        seen = set(self._state.get("seen_post_uuids", []))
        fetched_uuids = [post["post_uuid"] for post in posts if post.get("post_uuid")]

        if not self._state.get("initialized", False):
            self._mark_seen(fetched_uuids)
            self._state["initialized"] = True
            self._save_state()
            logger.info(
                f"NIKKE 首次初始化完成，已记录 {len(fetched_uuids)} 条历史消息。"
            )
            return ""

        new_posts = [post for post in posts if post.get("post_uuid") not in seen]
        if not new_posts:
            return f"无新帖({len(seen)})"

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
            return ""

        builder = MessageBuilder(self._config)
        seen_uuids: list[str] = []
        for idx, post in enumerate(new_posts):
            post_uuid = post.get("post_uuid")
            chain = builder.format_post_message_chain(post)

            ok = await broadcast_to_targets(targets, chain, "新闻")
            if post_uuid and ok:
                seen_uuids.append(post_uuid)

            delay = min(30, max(0, self._config.push_delay_seconds()))
            if delay > 0 and idx < len(new_posts) - 1:
                await asyncio.sleep(delay)

        if seen_uuids:
            self._mark_seen(seen_uuids)
            self._save_state()
            return f"已推送 {len(seen_uuids)} 条新帖"
        return ""
