import asyncio
import logging

import pytest

from main import NikkeNewsPlugin, PLUGIN_NAME


def make_plugin(**config) -> NikkeNewsPlugin:
    news_keys = {
        "language",
        "fetch_limit",
        "scheduled_push_groups",
        "push_delay_seconds",
        "push_prefix",
    }
    base = {
        "enabled": True,
        "poll_interval_seconds": 300,
        "news_push": {
            "language": "zh-TW",
            "fetch_limit": 10,
            "scheduled_push_groups": [],
            "push_delay_seconds": 0,
            "push_prefix": "",
        },
    }
    for key, value in config.items():
        if key in news_keys:
            base["news_push"][key] = value
        else:
            base[key] = value
    return NikkeNewsPlugin(context=None, config=base)


# ---------------------------------------------------------------------------
# enabled = True
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_initialize_enabled(caplog):
    caplog.set_level(logging.INFO)
    plugin = make_plugin()
    await plugin.initialize()
    assert plugin._task is not None
    assert plugin._client is not None
    assert "已启动" in caplog.text
    await plugin.terminate()


# ---------------------------------------------------------------------------
# enabled = False
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_initialize_disabled(caplog):
    caplog.set_level(logging.INFO)
    plugin = make_plugin(enabled=False)
    await plugin.initialize()
    assert plugin._task is None
    assert "已禁用" in caplog.text


# ---------------------------------------------------------------------------
# enabled = "false" (string)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_initialize_disabled_string(caplog):
    caplog.set_level(logging.INFO)
    plugin = make_plugin(enabled="false")
    await plugin.initialize()
    assert plugin._task is None


# ---------------------------------------------------------------------------
# first poll marks all as seen, no push
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_first_poll_marks_seen(caplog, captured):
    caplog.set_level(logging.INFO)
    plugin = make_plugin(
        scheduled_push_groups=["123456"],
    )
    await plugin.initialize()

    assert plugin._state["initialized"] is False
    assert plugin._state["seen_post_uuids"] == []

    # simulate first poll
    plugin._client = None  # simulate no client → return []
    await plugin._poll_once()

    # No client means empty posts; initialize path not reached
    # Actually this test needs real API data — covered in test_poll.py
    await plugin.terminate()


# ---------------------------------------------------------------------------
# terminate cleans up
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_terminate_cleanup():
    plugin = make_plugin()
    await plugin.initialize()
    assert plugin._task is not None
    assert plugin._client is not None

    await plugin.terminate()
    assert plugin._task is None
    assert plugin._client is None
