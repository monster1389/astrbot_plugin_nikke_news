import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.poll_coordinator import PollCoordinator
from main import NikkeNewsPlugin
from news.news_poller import NewsPoller
from player.player_poller import PlayerPoller


def _poll(plugin):
    poller = PlayerPoller(plugin._client, plugin._plugin_config, plugin._state, plugin._save_state)
    return poller.poll()


def make_plugin(**config) -> NikkeNewsPlugin:
    news_keys = {"scheduled_push_groups"}
    base = {
        "新闻": {"enabled": True, "scheduled_push_groups": ["123456"]},
        "玩家": {
            "状态提醒": {
                "enabled": True,
                "cookie": "cookie=abc",
                "daily_mission_remind_time": "00:00",
                "outpost_fullness_threshold_percent": 90,
                "daily_mission_enabled": True,
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
            base["玩家"]["状态提醒"]["cookie"] = value
        elif key == "player_daily_mission_remind_time":
            base["玩家"]["状态提醒"]["daily_mission_remind_time"] = value
        elif key == "outpost_fullness_threshold_percent":
            base["玩家"]["状态提醒"]["outpost_fullness_threshold_percent"] = value
        elif key == "daily_mission_enabled":
            base["玩家"]["状态提醒"]["daily_mission_enabled"] = value
        else:
            base[key] = value
    plugin = NikkeNewsPlugin(context=None, config=base)
    plugin._state = plugin._load_state()
    return plugin


def _mock_player_client(plugin, code=0, payload=None):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(
        return_value={
            "code": code,
            "msg": "err" if code else "ok",
            "data": payload
            or {
                "daily_progress": [
                    {
                        "outpost_battle_storage_fullness": 0.95,
                        "daily_mission_received_points": 0,
                    }
                ]
            },
        }
    )
    plugin._client = MagicMock()
    plugin._client.post = AsyncMock(return_value=mock_resp)


def _setup_coordinator(plugin):
    plugin._news_poller = NewsPoller(
        plugin._client, plugin._plugin_config,
        plugin._state, plugin._save_state, plugin._mark_seen,
    )
    plugin._player_poller = PlayerPoller(
        plugin._client, plugin._plugin_config,
        plugin._state, plugin._save_state,
    )
    plugin._coordinator = PollCoordinator(
        news_poller=plugin._news_poller,
        player_poller=plugin._player_poller,
        state=plugin._state,
        state_path=plugin._state_path,
        poll_interval_seconds=300,
    )


@pytest.mark.asyncio
async def test_player_data_disabled_does_not_call_api():
    plugin = make_plugin(player_data_enabled=False)
    plugin._client = MagicMock()
    plugin._client.post = AsyncMock()

    await _poll(plugin)

    plugin._client.post.assert_not_called()


@pytest.mark.asyncio
async def test_player_alerts_trigger_and_dedupe_same_day(captured):
    plugin = make_plugin()
    _mock_player_client(plugin)

    await _poll(plugin)
    first_count = len(captured)
    assert first_count == 1
    assert "超过阈值" in captured[0]["content"]
    assert "日常任务积分仍为 0" in captured[0]["content"]


@pytest.mark.asyncio
async def test_outpost_threshold_zero_disables_alert(captured):
    plugin = make_plugin(outpost_fullness_threshold_percent=0, daily_mission_enabled=False)
    _mock_player_client(plugin, payload={"outpost_battle_storage_fullness": 0.99, "daily_mission_received_points": 1})
    await _poll(plugin)
    assert len(captured) == 0

    await _poll(plugin)
    assert len(captured) == 0


@pytest.mark.asyncio
async def test_player_api_error_does_not_raise():
    plugin = make_plugin()
    _mock_player_client(plugin, code=1234)

    await _poll(plugin)


@pytest.mark.asyncio
async def test_player_poll_exception_does_not_break_news_flow(captured, tmp_path):
    plugin = make_plugin(player_data_cookie="cookie=abc", scheduled_push_groups=["123456"])
    plugin._state_path = tmp_path / "state.json"
    plugin._state_path.write_text(
        json.dumps({"initialized": True, "seen_post_uuids": ["old"]})
    )

    news_resp = MagicMock()
    news_resp.raise_for_status = MagicMock()
    news_resp.json = MagicMock(
        return_value={
            "code": 0,
            "data": {
                "list": [
                    {
                        "post_uuid": "new1",
                        "title": "News A",
                        "content_summary": "S",
                        "created_on": 1000,
                        "plate_id": 43,
                        "is_official": 1,
                    }
                ]
            },
        }
    )

    plugin._client = MagicMock()
    plugin._client.post = AsyncMock(side_effect=[news_resp, Exception("player err")])
    _setup_coordinator(plugin)

    await plugin._poll_once()

    assert any("News A" in item["content"] for item in captured)
