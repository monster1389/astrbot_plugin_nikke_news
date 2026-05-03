import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from main import NikkeNewsPlugin

API_RESPONSE = {
    "code": 0,
    "data": {
        "list": [
            {
                "post_uuid": "aaa1",
                "title": "Post A",
                "content_summary": "Summary A",
                "created_on": 1000,
                "plate_id": 43,
                "is_official": 1,
            },
            {
                "post_uuid": "bbb2",
                "title": "Post B",
                "content_summary": "Summary B",
                "created_on": 2000,
                "plate_id": 43,
                "is_official": 1,
            },
            {
                "post_uuid": "ccc3",
                "title": "Post C",
                "content_summary": "Summary C",
                "created_on": 3000,
                "plate_id": 43,
                "is_official": 1,
            },
        ]
    },
}


def make_plugin(**config) -> NikkeNewsPlugin:
    base = {
        "enabled": True,
        "poll_interval_seconds": 300,
        "language": "zh-TW",
        "fetch_limit": 10,
        "scheduled_push_groups": ["123456"],
        "push_delay_seconds": 0,
        "push_prefix": "",
    }
    base.update(config)
    plugin = NikkeNewsPlugin(context=None, config=base)
    return plugin


def _mock_client(plugin, response=None, error=None):
    if error:
        plugin._client = MagicMock()
        plugin._client.post = AsyncMock(side_effect=error)
    else:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=response or API_RESPONSE)
        plugin._client = MagicMock()
        plugin._client.post = AsyncMock(return_value=mock_resp)


# ---------------------------------------------------------------------------
# first poll: initialized=false → mark all as seen, no push
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_first_poll_initializes(caplog, captured, tmp_path):
    caplog.set_level(logging.INFO)
    plugin = make_plugin()
    plugin._state_path = tmp_path / "state.json"
    plugin._state = plugin._load_state()
    assert plugin._state["initialized"] is False

    _mock_client(plugin)

    await plugin._poll_once()

    assert plugin._state["initialized"] is True
    assert len(plugin._state["seen_post_uuids"]) == 3
    assert "首次初始化完成" in caplog.text
    assert len(captured) == 0


# ---------------------------------------------------------------------------
# subsequent poll: no new posts
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_no_new_posts(caplog, captured, tmp_path):
    caplog.set_level(logging.DEBUG)
    plugin = make_plugin()
    plugin._state_path = tmp_path / "state.json"
    # write disk state: initialized, all 3 seen
    plugin._state_path.write_text(
        json.dumps({"initialized": True, "seen_post_uuids": ["aaa1", "bbb2", "ccc3"]})
    )

    _mock_client(plugin)

    await plugin._poll_once()

    assert "无新帖" in caplog.text
    assert len(captured) == 0


# ---------------------------------------------------------------------------
# new posts detected → push
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_new_posts_pushes(caplog, captured, tmp_path):
    caplog.set_level(logging.INFO)
    plugin = make_plugin()
    plugin._state_path = tmp_path / "state.json"
    plugin._state_path.write_text(
        json.dumps({"initialized": True, "seen_post_uuids": ["bbb2"]})
    )

    _mock_client(plugin)

    await plugin._poll_once()

    assert "发现新帖" in caplog.text
    assert len(captured) == 2
    assert "Post A" in captured[0]["content"]
    assert "Post C" in captured[1]["content"]


# ---------------------------------------------------------------------------
# API exception → propagates (caught by _poll_loop in real usage)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_api_timeout(caplog, tmp_path):
    plugin = make_plugin()
    plugin._state_path = tmp_path / "state.json"
    plugin._state_path.write_text(
        json.dumps({"initialized": True, "seen_post_uuids": []})
    )
    _mock_client(plugin, error=Exception("ReadTimeout"))

    with pytest.raises(Exception, match="ReadTimeout"):
        await plugin._poll_once()


# ---------------------------------------------------------------------------
# API returns empty list → warning
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_api_empty_list(caplog, tmp_path):
    caplog.set_level(logging.WARNING)
    plugin = make_plugin()
    plugin._state_path = tmp_path / "state.json"
    plugin._state_path.write_text(
        json.dumps({"initialized": True, "seen_post_uuids": []})
    )
    _mock_client(plugin, response={"code": 0, "data": {"list": []}})

    await plugin._poll_once()
    assert "未获取到任何帖子" in caplog.text


# ---------------------------------------------------------------------------
# API code != 0 → propagates
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_api_error_code(tmp_path):
    plugin = make_plugin()
    plugin._state_path = tmp_path / "state.json"
    plugin._state_path.write_text(
        json.dumps({"initialized": True, "seen_post_uuids": []})
    )
    _mock_client(
        plugin, response={"code": 500, "msg": "error"}
    )

    with pytest.raises(RuntimeError, match="Blablalink API 返回错误"):
        await plugin._poll_once()


# ---------------------------------------------------------------------------
# re-reads state from disk each poll
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_rereads_state_from_disk(caplog, captured, tmp_path):
    caplog.set_level(logging.INFO)
    plugin = make_plugin()
    plugin._state_path = tmp_path / "state.json"
    plugin._state_path.write_text(
        json.dumps({"initialized": True, "seen_post_uuids": ["bbb2"]})
    )

    _mock_client(plugin)

    await plugin._poll_once()

    assert "发现新帖" in caplog.text
    assert len(captured) == 2


# ---------------------------------------------------------------------------
# filters non-official / wrong plate_id posts
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_filters_non_official(caplog, captured, tmp_path):
    caplog.set_level(logging.INFO)
    plugin = make_plugin()
    plugin._state_path = tmp_path / "state.json"
    plugin._state_path.write_text(
        json.dumps({"initialized": True, "seen_post_uuids": []})
    )

    mixed = {
        "code": 0,
        "data": {
            "list": [
                {
                    "post_uuid": "off1",
                    "title": "Not Official",
                    "content_summary": "",
                    "created_on": 100,
                    "plate_id": 99,
                    "is_official": 1,
                },
                {
                    "post_uuid": "off2",
                    "title": "Unofficial",
                    "content_summary": "",
                    "created_on": 200,
                    "plate_id": 43,
                    "is_official": 0,
                },
                {
                    "post_uuid": "ok1",
                    "title": "Valid",
                    "content_summary": "",
                    "created_on": 300,
                    "plate_id": 43,
                    "is_official": 1,
                },
            ]
        },
    }
    _mock_client(plugin, response=mixed)

    await plugin._poll_once()
    assert len(captured) == 1
    assert "Valid" in captured[0]["content"]
