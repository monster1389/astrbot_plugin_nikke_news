"""轮询调度：协调新闻轮询与玩家状态轮询的执行周期。"""

import asyncio
from typing import Any

from astrbot.api import logger

from news.news_poller import NewsPoller
from player.player_poller import PlayerPoller
from core.state_store import PluginStateStore


class PollCoordinator:
    """轮询调度器，按配置间隔循环执行新闻与玩家轮询。

    Attributes:
        _news_poller: 新闻轮询器实例。
        _player_poller: 玩家状态轮询器实例。
        _state: 插件状态 dict（共享引用）。
        _state_path: state.json 文件路径。
        _poll_interval_seconds: 轮询间隔秒数。
    """

    def __init__(
        self,
        news_poller: NewsPoller,
        player_poller: PlayerPoller,
        state: dict[str, Any],
        state_path: Any,
        poll_interval_seconds: int,
    ):
        self._news_poller = news_poller
        self._player_poller = player_poller
        self._state = state
        self._state_path = state_path
        self._poll_interval_seconds = poll_interval_seconds

    async def run(self):
        """启动轮询循环，每 poll_interval_seconds 秒执行一次 _poll_once。

        循环内部捕获非取消异常，确保单次失败不中断后续轮询。
        """
        logger.info("NIKKE 轮询循环已开始。")
        while True:
            loop = asyncio.get_running_loop()
            start = loop.time()
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    f"NIKKE 轮询异常（{type(exc).__name__}），将在下次重试：{exc}",
                    exc_info=True,
                )

            elapsed = loop.time() - start
            await asyncio.sleep(max(0, self._poll_interval_seconds - elapsed))

    async def _poll_once(self):
        """单次轮询：重读磁盘状态 → 新闻 → 玩家数据，两者独立容错。"""
        self._state.clear()
        self._state.update(PluginStateStore(self._state_path).load())
        try:
            await self._news_poller.poll()
        except Exception as exc:
            logger.warning(f"NIKKE 新闻轮询异常，将在下次重试：{exc}", exc_info=True)
        try:
            await self._player_poller.poll()
        except Exception as exc:
            logger.warning(
                f"NIKKE 玩家数据轮询异常，将在下次重试：{exc}", exc_info=True
            )
