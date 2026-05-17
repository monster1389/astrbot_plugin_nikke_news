"""消息格式化：新闻推送消息链、玩家提醒消息。"""

from datetime import datetime
from typing import Any

from astrbot.api.event import MessageChain
import astrbot.api.message_components as Comp

from .config import PluginConfig
from .constants import CST, POST_DETAIL_URL, SUMMARY_MAX_LENGTH
from .utils import (
    clean_html_with_linebreaks,
    clean_text,
    format_timestamp,
    is_video_post,
)


class MessageBuilder:
    """构建推送消息链和玩家提醒消息文本。"""

    def __init__(self, config: PluginConfig):
        self._config = config

    def format_post_message(self, post: dict[str, Any]) -> str:
        """构建单条推送消息文本（标题+正文+时间戳+详情链接）。"""
        title = clean_text(post.get("title")) or "NIKKE 官方消息"
        body = self._format_post_body(post)

        created_on = format_timestamp(post.get("created_on"))
        detail_url = POST_DETAIL_URL.format(post_uuid=post.get("post_uuid", ""))

        prefix = self._config.push_prefix()
        parts = [prefix, title] if prefix else [title]
        if body:
            parts.append(body)
        if self._config.show_publish_time():
            parts.append(f"发布时间：{created_on}")
        parts.append(f"链接：{detail_url}")
        return "\n\n".join(parts)

    def format_post_message_chain(self, post: dict[str, Any]) -> MessageChain:
        """构建新闻推送消息链（文本 + 图片）。"""
        chain = MessageChain().message(self.format_post_message(post))
        for image_url in self.post_image_urls(post):
            chain.chain.append(Comp.Image.fromURL(image_url))
        return chain

    def _format_post_body(self, post: dict[str, Any]) -> str:
        mode = self._config.content_mode()
        if mode == "none":
            return ""

        if mode == "content":
            return clean_html_with_linebreaks(post.get("content"))

        summary = clean_text(post.get("content_summary"))
        if len(summary) > SUMMARY_MAX_LENGTH:
            summary = summary[:SUMMARY_MAX_LENGTH].rstrip() + "..."
        return summary

    def post_image_urls(self, post: dict[str, Any]) -> list[str]:
        if is_video_post(post):
            return []

        max_images = self._config.max_images()
        if max_images <= 0:
            return []

        pic_urls = post.get("pic_urls", [])
        if not isinstance(pic_urls, list):
            return []

        urls: list[str] = []
        for value in pic_urls:
            url = str(value or "").strip()
            if not url.startswith(("http://", "https://")) or url in urls:
                continue
            urls.append(url)
            if len(urls) >= max_images:
                break
        return urls

    def format_player_alert_message(self, lines: list[str]) -> str:
        """构建玩家状态提醒消息文本。"""
        prefix = self._config.player_alert_prefix()
        parts = [prefix] if prefix else []
        parts.extend(lines)
        parts.append(f"时间：{datetime.now(CST).strftime('%Y-%m-%d %H:%M')} (UTC+8)")
        return "\n\n".join(parts)
