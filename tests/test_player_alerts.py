from unittest.mock import AsyncMock, MagicMock

import pytest

from main import NikkeNewsPlugin
from player.player_poller import PlayerPoller


def make_plugin(**config) -> NikkeNewsPlugin:
    news_keys = {"scheduled_push_groups"}
    base = {
        "新闻": {"enabled": True, "scheduled_push_groups": ["123456"]},
        "玩家": {
            "cookie": {"game_token": "abc"},
            "状态提醒": {
                "enabled": True,
                "daily_mission_remind_time": "23:59",
                "outpost_fullness_threshold_percent": 0,
                "daily_mission_enabled": False,
            },
            "nikke查询": {},
        },
    }
    for key, value in config.items():
        if key in news_keys:
            base["新闻"][key] = value
        elif key == "player_data_enabled":
            base["玩家"]["状态提醒"]["enabled"] = value
        elif key == "player_data_cookie":
            base["玩家"]["cookie"] = value
        elif key == "player_daily_mission_remind_time":
            base["玩家"]["状态提醒"]["daily_mission_remind_time"] = value
        elif key == "player_remind_daily_mission_enabled":
            base["玩家"]["状态提醒"]["daily_mission_enabled"] = value
        elif key == "outpost_fullness_threshold_percent":
            base["玩家"]["状态提醒"]["outpost_fullness_threshold_percent"] = value
        else:
            base[key] = value
    plugin = NikkeNewsPlugin(context=None, config=base)
    plugin._state = plugin._load_state()
    return plugin


def _poll(plugin):
    poller = PlayerPoller(
        plugin._client, plugin._plugin_config, plugin._state, plugin._save_state
    )
    return poller.poll()


def _response(code=0):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(
        return_value={
            "code": code,
            "msg": "invalid" if code else "ok",
            "data": {
                "outpost_battle_storage_fullness": 0.1,
                "daily_mission_received_points": 100,
            },
        }
    )
    return resp


@pytest.mark.asyncio
async def test_cookie_invalid_first_chat_then_log_only(captured):
    plugin = make_plugin()
    plugin._client = MagicMock()
    plugin._client.post = AsyncMock(return_value=_response(code=1001))

    await _poll(plugin)
    assert len(captured) == 1
    assert "登录态已失效" in captured[0]["content"]

    await _poll(plugin)
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_cookie_invalid_resets_after_recovery(captured):
    plugin = make_plugin()
    plugin._client = MagicMock()
    plugin._client.post = AsyncMock(
        side_effect=[
            _response(code=1001),
            _response(code=0),
            _response(code=1001),
        ]
    )

    await _poll(plugin)
    await _poll(plugin)
    await _poll(plugin)

    assert len(captured) == 2
    assert "登录态已失效" in captured[0]["content"]
    assert "登录态已失效" in captured[1]["content"]


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_day_key_uses_4am_boundary():
    from datetime import datetime, timedelta, timezone

    from core.time_utils import day_key

    cst = timezone(timedelta(hours=8))
    assert day_key(datetime(2026, 5, 8, 3, 59, tzinfo=cst)) == "2026-05-07"
    assert day_key(datetime(2026, 5, 8, 4, 0, tzinfo=cst)) == "2026-05-08"
