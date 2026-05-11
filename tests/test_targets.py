import logging

import pytest

from main import NikkeNewsPlugin
from core.targets import enabled_targets, parse_push_target


def make_plugin(**config) -> NikkeNewsPlugin:
    news_keys = {"scheduled_push_groups", "targets"}
    base = {
        "enabled": True,
        "news_push": {"scheduled_push_groups": []},
    }
    for key, value in config.items():
        if key in news_keys:
            base["news_push"][key] = value
        else:
            base[key] = value
    plugin = NikkeNewsPlugin(context=None, config=base)
    return plugin


# ---------------------------------------------------------------------------
# parse_push_target
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value, expected",
    [
        ("123456", {"target_type": "GroupMessage", "target_id": "123456"}),
        (
            "aiocqhttp:GroupMessage:957880653",
            {"target_type": "GroupMessage", "target_id": "957880653"},
        ),
        (
            "napcat:FriendMessage:2854964693",
            {"target_type": "FriendMessage", "target_id": "2854964693"},
        ),
        (
            "napcat:PrivateMessage:999",
            {"target_type": "PrivateMessage", "target_id": "999"},
        ),
        ("not-a-number", None),
        ("a:b:c", None),
        ("", None),
        ("just:GroupMessage:123", {"target_type": "GroupMessage", "target_id": "123"}),
    ],
)
def test_parse_push_target(value, expected):
    result = parse_push_target(value)
    assert result == expected


# ---------------------------------------------------------------------------
# enabled_targets – new format
# ---------------------------------------------------------------------------
def test_enabled_targets_new_format():
    plugin = make_plugin(
        scheduled_push_groups=["111", "222", "napcat:FriendMessage:333"]
    )
    targets = enabled_targets(plugin._plugin_config.news_config())
    assert len(targets) == 3
    assert targets[0] == {"target_type": "GroupMessage", "target_id": "111"}
    assert targets[2] == {"target_type": "FriendMessage", "target_id": "333"}


# ---------------------------------------------------------------------------
# enabled_targets – invalid entries skipped
# ---------------------------------------------------------------------------
def test_enabled_targets_skips_invalid(caplog):
    caplog.set_level(logging.WARNING)
    plugin = make_plugin(scheduled_push_groups=["111", "badformat", ""])
    targets = enabled_targets(plugin._plugin_config.news_config())
    assert len(targets) == 1
    assert "跳过无效推送目标" in caplog.text


# ---------------------------------------------------------------------------
# enabled_targets – legacy format fallback
# ---------------------------------------------------------------------------
def test_enabled_targets_legacy():
    plugin = make_plugin(
        scheduled_push_groups=[],
        targets=[
            {"target_type": "GroupMessage", "target_id": "111", "enabled": True},
            {"target_type": "PrivateMessage", "target_id": "222", "enabled": True},
        ],
    )
    targets = enabled_targets(plugin._plugin_config.news_config())
    assert len(targets) == 2


# ---------------------------------------------------------------------------
# enabled_targets – legacy disabled skipped
# ---------------------------------------------------------------------------
def test_enabled_targets_legacy_disabled():
    plugin = make_plugin(
        scheduled_push_groups=[],
        targets=[
            {"target_type": "GroupMessage", "target_id": "111", "enabled": False},
        ],
    )
    targets = enabled_targets(plugin._plugin_config.news_config())
    assert len(targets) == 0
