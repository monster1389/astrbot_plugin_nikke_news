from unittest.mock import AsyncMock, MagicMock

import pytest

from main import NikkeNewsPlugin


def make_plugin(**config) -> NikkeNewsPlugin:
    news_keys = {"scheduled_push_groups"}
    base = {
        "enabled": True,
        "news_push": {"scheduled_push_groups": ["123456"]},
        "player_reminder": {
            "enabled": True,
            "cookie": "cookie=abc",
            "daily_mission_remind_time": "23:59",
            "outpost_fullness_threshold_percent": 0,
            "daily_mission_enabled": False,
        },
    }
    for key, value in config.items():
        if key in news_keys:
            base["news_push"][key] = value
        elif key == "player_data_enabled":
            base["player_reminder"]["enabled"] = value
        elif key == "player_data_cookie":
            base["player_reminder"]["cookie"] = value
        elif key == "player_daily_mission_remind_time":
            base["player_reminder"]["daily_mission_remind_time"] = value
        elif key == "player_remind_daily_mission_enabled":
            base["player_reminder"]["daily_mission_enabled"] = value
        elif key == "outpost_fullness_threshold_percent":
            base["player_reminder"]["outpost_fullness_threshold_percent"] = value
        else:
            base[key] = value
    plugin = NikkeNewsPlugin(context=None, config=base)
    plugin._state = plugin._load_state()
    return plugin


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

    await plugin._poll_player_once()
    assert len(captured) == 1
    assert "登录态已失效" in captured[0]["content"]

    await plugin._poll_player_once()
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

    await plugin._poll_player_once()
    await plugin._poll_player_once()
    await plugin._poll_player_once()

    assert len(captured) == 2
    assert "登录态已失效" in captured[0]["content"]
    assert "登录态已失效" in captured[1]["content"]


@pytest.mark.asyncio
async def test_day_key_uses_4am_boundary():
    plugin = make_plugin()

    from datetime import datetime, timedelta, timezone

    cst = timezone(timedelta(hours=8))
    assert plugin._day_key(datetime(2026, 5, 8, 3, 59, tzinfo=cst)) == "2026-05-07"
    assert plugin._day_key(datetime(2026, 5, 8, 4, 0, tzinfo=cst)) == "2026-05-08"
