import json
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
            "daily_mission_remind_time": "00:00",
            "outpost_fullness_threshold_percent": 90,
            "daily_mission_enabled": True,
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
        elif key == "outpost_fullness_threshold_percent":
            base["player_reminder"]["outpost_fullness_threshold_percent"] = value
        elif key == "daily_mission_enabled":
            base["player_reminder"]["daily_mission_enabled"] = value
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
                "outpost_battle_storage_fullness": 0.95,
                "daily_mission_received_points": 0,
            },
        }
    )
    plugin._client = MagicMock()
    plugin._client.post = AsyncMock(return_value=mock_resp)


@pytest.mark.asyncio
async def test_player_data_disabled_does_not_call_api():
    plugin = make_plugin(player_data_enabled=False)
    plugin._client = MagicMock()
    plugin._client.post = AsyncMock()

    await plugin._poll_player_once()

    plugin._client.post.assert_not_called()


@pytest.mark.asyncio
async def test_player_alerts_trigger_and_dedupe_same_day(captured):
    plugin = make_plugin()
    _mock_player_client(plugin)

    await plugin._poll_player_once()
    first_count = len(captured)
    assert first_count == 1
    assert "超过阈值" in captured[0]["content"]
    assert "日常任务积分仍为 0" in captured[0]["content"]


@pytest.mark.asyncio
async def test_outpost_threshold_zero_disables_alert(captured):
    plugin = make_plugin(outpost_fullness_threshold_percent=0, daily_mission_enabled=False)
    _mock_player_client(plugin, payload={"outpost_battle_storage_fullness": 0.99, "daily_mission_received_points": 1})
    await plugin._poll_player_once()
    assert len(captured) == 0

    await plugin._poll_player_once()
    assert len(captured) == 0


@pytest.mark.asyncio
async def test_player_api_error_does_not_raise():
    plugin = make_plugin()
    _mock_player_client(plugin, code=1234)

    await plugin._poll_player_once()


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

    await plugin._poll_once()

    assert any("News A" in item["content"] for item in captured)
