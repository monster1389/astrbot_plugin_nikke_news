import asyncio
from typing import Any

from astrbot.api import logger

from news.news_poller import NewsPoller
from player.player_poller import PlayerPoller
from core.state_store import PluginStateStore


class PollCoordinator:
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

            await asyncio.sleep(self._poll_interval_seconds)

    async def _poll_once(self):
        self._state.clear()
        self._state.update(PluginStateStore(self._state_path).load())
        await self._news_poller.poll()
        try:
            await self._player_poller.poll()
        except Exception as exc:
            logger.warning(f"NIKKE 玩家数据轮询异常，将在下次重试：{exc}")

    def load_state(self) -> dict[str, Any]:
        return PluginStateStore(self._state_path).load()

    def save_state(self):
        PluginStateStore(self._state_path).save(self._state)

    @staticmethod
    def mark_seen(state: dict[str, Any], post_uuids: list[str]):
        PluginStateStore.mark_seen(state, post_uuids)
