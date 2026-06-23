# core/cache_refresher.py
"""缓存刷新调度：并发刷新角色映射与头像映射。"""

import asyncio
import time

from astrbot.api import logger
from core.cookie_status import CookieStatus


def _unwrap(result, label: str) -> str:
    if isinstance(result, Exception):
        logger.warning(f"NIKKE {label}刷新失败：{result}", exc_info=True)
        return f"{label}刷新失败：{result}"
    if isinstance(result, tuple):
        msg, _ = result
        return msg or f"{label}：无需刷新。"
    return str(result or f"{label}：无需刷新。")


class CacheRefresher:
    """并发调度角色映射和头像映射的 TTL/强制刷新。"""

    def __init__(self, character_service, avatar_service, player_poller, config):
        self._character_service = character_service
        self._avatar_service = avatar_service
        self._player_poller = player_poller
        self._config = config
        self._in_progress = False

    async def refresh(self, force: bool = False) -> str | None:
        """并发刷新角色映射和头像映射。

        Args:
            force: True 跳过 TTL 检查强制刷新，False 仅过期时刷新。

        Returns:
            结果消息字符串（含耗时），或 None（cookie 不可用 / 并发冲突）。
        """
        if self._in_progress:
            return None
        self._in_progress = True
        try:
            if self._player_poller.cookie_status() != CookieStatus.AVAILABLE:
                return None

            t0 = time.monotonic()
            cookie = self._config.player_data_cookie()
            results = await asyncio.gather(
                self._character_service.refresh_mappings(force=force),
                self._avatar_service.refresh_cached(cookie),
                return_exceptions=True,
            )
            role_msg = _unwrap(results[0], "角色映射")
            avatar_msg = _unwrap(results[1], "头像")
            elapsed = time.monotonic() - t0
            return f"{role_msg}\n{avatar_msg}\n总耗时 {elapsed:.0f}s"
        finally:
            self._in_progress = False
