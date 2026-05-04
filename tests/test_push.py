import json
import logging
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
                "pic_urls": [
                    "https://example.com/a1.png",
                    "https://example.com/a2.png",
                    "https://example.com/a3.png",
                    "https://example.com/a4.png",
                ],
                "type": 1,
            },
            {
                "post_uuid": "bbb2",
                "title": "Post B",
                "content_summary": "Summary B",
                "created_on": 2000,
                "plate_id": 43,
                "is_official": 1,
                "pic_urls": [],
                "type": 1,
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
    return NikkeNewsPlugin(context=None, config=base)


def _mock_client(plugin, response=None):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=response or API_RESPONSE)
    plugin._client = MagicMock()
    plugin._client.post = AsyncMock(return_value=mock_resp)


def _write_state(tmp_path, seen):
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.write_text(
        json.dumps({"initialized": True, "seen_post_uuids": seen})
    )


# ---------------------------------------------------------------------------
# image push – defaults to at most 3 images
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_push_images_default_max_three(captured, tmp_path):
    state_path = tmp_path / "state.json"
    plugin = make_plugin()
    plugin._state_path = state_path
    _write_state(state_path, ["bbb2"])
    _mock_client(plugin)

    await plugin._poll_once()

    assert captured[0]["image_urls"] == [
        "https://example.com/a1.png",
        "https://example.com/a2.png",
        "https://example.com/a3.png",
    ]


# ---------------------------------------------------------------------------
# image push – max_images can limit or disable images
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_push_images_respects_max_images(captured, tmp_path):
    state_path = tmp_path / "state.json"
    plugin = make_plugin(max_images=1)
    plugin._state_path = state_path
    _write_state(state_path, ["bbb2"])
    _mock_client(plugin)

    await plugin._poll_once()

    assert captured[0]["image_urls"] == ["https://example.com/a1.png"]


@pytest.mark.asyncio
async def test_push_images_can_be_disabled(captured, tmp_path):
    state_path = tmp_path / "state.json"
    plugin = make_plugin(max_images=0)
    plugin._state_path = state_path
    _write_state(state_path, ["bbb2"])
    _mock_client(plugin)

    await plugin._poll_once()

    assert captured[0]["image_urls"] == []


# ---------------------------------------------------------------------------
# video posts do not send images
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_push_video_post_skips_images(captured, tmp_path):
    state_path = tmp_path / "state.json"
    plugin = make_plugin()
    plugin._state_path = state_path
    _write_state(state_path, [])
    response = {
        "code": 0,
        "data": {
            "list": [
                {
                    "post_uuid": "vid1",
                    "title": "Video",
                    "content_summary": "Summary",
                    "created_on": 1000,
                    "plate_id": 43,
                    "is_official": 1,
                    "type": 3,
                    "pic_urls": ["https://example.com/cover.png"],
                    "ext_info": '[{"video_cover":"https://example.com/video.jpg"}]',
                }
            ]
        },
    }
    _mock_client(plugin, response=response)

    await plugin._poll_once()

    assert captured[0]["image_urls"] == []


# ---------------------------------------------------------------------------
# push_delay_seconds = 0 → no delay between posts
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_push_no_delay(captured, tmp_path):
    state_path = tmp_path / "state.json"
    plugin = make_plugin(push_delay_seconds=0)
    plugin._state_path = state_path
    _write_state(state_path, [])
    _mock_client(plugin)

    await plugin._poll_once()
    assert len(captured) == 2


# ---------------------------------------------------------------------------
# push_delay_seconds = 1 → asyncio.sleep called between posts
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_push_with_delay(tmp_path):
    state_path = tmp_path / "state.json"
    plugin = make_plugin(push_delay_seconds=1)
    plugin._state_path = state_path
    _write_state(state_path, [])
    _mock_client(plugin)

    import main as mod

    sleeps = []
    mp = pytest.MonkeyPatch()
    mp.setattr(mod.asyncio, "sleep", AsyncMock(side_effect=lambda s: sleeps.append(s)))

    await plugin._poll_once()

    mp.undo()
    assert len(sleeps) == 1
    assert sleeps[0] == 1


# ---------------------------------------------------------------------------
# push_prefix prepended
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_push_prefix(captured, tmp_path):
    state_path = tmp_path / "state.json"
    plugin = make_plugin(push_prefix="【TEST】")
    plugin._state_path = state_path
    _write_state(state_path, [])
    _mock_client(plugin)

    await plugin._poll_once()
    assert captured[0]["content"].startswith("【TEST】")


# ---------------------------------------------------------------------------
# push_prefix empty → no prefix, title first
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_push_prefix_empty(captured, tmp_path):
    state_path = tmp_path / "state.json"
    plugin = make_plugin(push_prefix="")
    plugin._state_path = state_path
    _write_state(state_path, [])
    _mock_client(plugin)

    await plugin._poll_once()
    assert captured[0]["content"].startswith("Post A")


# ---------------------------------------------------------------------------
# push target type = FriendMessage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_push_friend_message(captured, tmp_path):
    state_path = tmp_path / "state.json"
    plugin = make_plugin(scheduled_push_groups=["napcat:FriendMessage:2854964693"])
    plugin._state_path = state_path
    _write_state(state_path, [])
    _mock_client(plugin)

    await plugin._poll_once()
    assert captured[0]["target_type"] == "FriendMessage"
    assert captured[0]["target_id"] == "2854964693"


# ---------------------------------------------------------------------------
# multiple targets – one post delivered to all
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_push_multiple_targets(captured, tmp_path):
    state_path = tmp_path / "state.json"
    plugin = make_plugin(scheduled_push_groups=["111", "222"])
    plugin._state_path = state_path
    _write_state(state_path, [])
    _mock_client(plugin)

    await plugin._poll_once()
    assert len(captured) == 4
    ids = {m["target_id"] for m in captured}
    assert ids == {"111", "222"}


# ---------------------------------------------------------------------------
# no targets → mark new as seen, warn
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_push_no_targets(caplog, captured, tmp_path):
    caplog.set_level(logging.WARNING)
    state_path = tmp_path / "state.json"
    plugin = make_plugin(scheduled_push_groups=[])
    plugin._state_path = state_path
    _write_state(state_path, [])
    _mock_client(plugin)

    await plugin._poll_once()
    assert "未配置推送目标" in caplog.text
    assert len(captured) == 0
    assert len(plugin._state["seen_post_uuids"]) == 2


# ---------------------------------------------------------------------------
# send failure on one target doesn't block others
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_push_partial_failure(caplog, captured, tmp_path):
    caplog.set_level(logging.WARNING)
    state_path = tmp_path / "state.json"
    plugin = make_plugin(scheduled_push_groups=["111", "222"])
    plugin._state_path = state_path
    _write_state(state_path, [])
    _mock_client(plugin)

    import main as mod

    call_count = 0
    original = mod.StarTools.send_message_by_id

    async def flaky_send(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("send failed")
        return await original(*args, **kwargs)

    mod.StarTools.send_message_by_id = flaky_send

    try:
        await plugin._poll_once()
        assert "消息发送失败" in caplog.text
        assert len(captured) == 3
    finally:
        mod.StarTools.send_message_by_id = original
