from datetime import datetime
from typing import Any, Callable

import httpx
from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.star import StarTools

from core.config import PluginConfig
from core.constants import CST
from core.message_builder import MessageBuilder
from player.player_client import PlayerClient
from core.targets import enabled_targets
from core.time_utils import day_key, is_cookie_invalid_error
from core.utils import safe_float, safe_int


class PlayerPoller:
    """周期检查玩家前哨满仓状态和日常完成情况，按阈值发送提醒。"""

    def __init__(
        self,
        client: httpx.AsyncClient | None,
        config: PluginConfig,
        state: dict[str, Any],
        save_state: Callable[[], None],
    ):
        self._client = client
        self._config = config
        self._state = state
        self._save_state = save_state

    async def poll(self) -> None:
        """检查前哨基地满仓 & 日常任务完成情况，必要时推送提醒。"""
        if not self._config.player_data_enabled():
            return

        cookie = self._config.player_data_cookie()
        if not cookie:
            logger.warning("NIKKE 玩家数据功能已启用，但未配置玩家状态提醒的 Cookie。")
            return

        targets = enabled_targets(self._config.news_config())
        if not targets:
            logger.warning("NIKKE 玩家数据功能已启用，但未配置推送目标。")
            return

        player_state = self._state.setdefault("player_alert_state", {})
        player_state.setdefault("cookie_invalid_notified", False)
        player_state.setdefault("last_outpost_alert_day_key", "")
        player_state.setdefault("last_daily_mission_alert_day_key", "")

        try:
            area_id = self._config.player_data_area_id()
            data = await PlayerClient(self._client).fetch_progress(cookie, area_id)
            if player_state.get("cookie_invalid_notified"):
                player_state["cookie_invalid_notified"] = False
                self._save_state()
        except Exception as exc:
            if is_cookie_invalid_error(exc):
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
        today_key = day_key(now)
        remind_time = self._config.player_daily_mission_remind_time()
        remind_dt = datetime.combine(now.date(), remind_time, tzinfo=CST)

        lines: list[str] = []
        save_needed = False

        daily_list = data.get("daily_progress") or []
        daily = (
            daily_list[0]
            if isinstance(daily_list, list) and len(daily_list) > 0
            else {}
        )

        fullness = safe_float(daily.get("outpost_battle_storage_fullness"))
        fullness_percent = fullness * 100
        points = safe_int(daily.get("daily_mission_received_points"))

        threshold = self._config.outpost_fullness_threshold_percent()
        if threshold > 0:
            last_day = str(player_state.get("last_outpost_alert_day_key", ""))
            if fullness_percent >= threshold and last_day != today_key:
                lines.append(
                    f"前哨基地存储 {fullness_percent:.0f}%，已达到/超过阈值 {threshold}%，建议尽快上线收菜。"
                )
                player_state["last_outpost_alert_day_key"] = today_key
                save_needed = True

        if self._config.player_remind_daily_mission_enabled():
            last_day = str(player_state.get("last_daily_mission_alert_day_key", ""))
            if points == 0 and now >= remind_dt and last_day != today_key:
                lines.append("今日日常任务积分仍为 0，请记得完成日常。")
                player_state["last_daily_mission_alert_day_key"] = today_key
                save_needed = True

        if lines:
            await self._send_player_alert(targets, lines)

        if save_needed:
            self._save_state()

        logger.debug(
            f"NIKKE 玩家数据轮询完成（前哨 {fullness_percent:.0f}%，"
            f"日常积分 {points}）。"
        )

    async def _send_player_alert(
        self, targets: list[dict[str, str]], lines: list[str]
    ) -> None:
        """向所有目标群发送玩家状态提醒。"""
        builder = MessageBuilder(self._config)
        chain = MessageChain().message(builder.format_player_alert_message(lines))
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
