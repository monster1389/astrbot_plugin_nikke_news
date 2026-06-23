# core/cache_refresher.py
"""缓存刷新调度：并发刷新角色映射与头像映射。"""

import asyncio
import time

from core.cookie_status import CookieStatus


class CacheRefresher:
    """并发调度角色映射和头像映射的 TTL/强制刷新。"""

    def __init__(self, character_service, avatar_service, player_poller, config):
        self._character_service = character_service
        self._avatar_service = avatar_service
        self._player_poller = player_poller
        self._config = config
        self._in_progress = False

    async def refresh(
        self,
        force: bool = False,
        skip_character: bool = False,
        skip_avatar: bool = False,
    ) -> tuple[str, bool, bool] | None:
        """并发刷新角色映射和头像映射。

        Args:
            force: True 跳过 TTL 检查强制刷新。
            skip_character: True 跳过角色映射刷新。
            skip_avatar: True 跳过头像映射刷新。

        Returns:
            (消息文本, 角色是否失败, 头像是否失败)，不可用时返回 None。
        """
        if self._in_progress:
            return None
        self._in_progress = True
        try:
            if self._player_poller.cookie_status() != CookieStatus.AVAILABLE:
                return None

            t0 = time.monotonic()
            cookie = self._config.player_data_cookie()

            async def _noop():
                return ("", False)

            char_task = (
                _noop()
                if skip_character
                else self._character_service.refresh_mappings(force=force)
            )
            avatar_task = (
                _noop()
                if skip_avatar
                else self._avatar_service.refresh_cached(cookie, force=force)
            )

            results = await asyncio.gather(
                char_task, avatar_task, return_exceptions=True
            )

            if isinstance(results[0], Exception):
                role_msg = f"角色映射刷新失败：{results[0]}"
                char_failed = True
            else:
                role_msg, char_failed = results[0]

            if isinstance(results[1], Exception):
                avatar_msg = f"头像刷新失败：{results[1]}"
                avatar_failed = True
            else:
                avatar_msg, avatar_failed = results[1]

            parts = [p for p in [role_msg, avatar_msg] if p]
            has_failure = char_failed or avatar_failed
            if has_failure:
                parts.append("请执行 /nikke_refresh 重置失败状态后重试。")
            elapsed = time.monotonic() - t0
            parts.append(f"总耗时 {elapsed:.0f}s")
            return ("\n".join(parts), char_failed, avatar_failed)
        finally:
            self._in_progress = False
