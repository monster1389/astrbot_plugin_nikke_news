import json
import logging
from pathlib import Path

import pytest

from main import NikkeNewsPlugin


def make_plugin(**config) -> NikkeNewsPlugin:
    base = {"enabled": True}
    base.update(config)
    return NikkeNewsPlugin(context=None, config=base)


# ---------------------------------------------------------------------------
# _load_state – file doesn't exist → default
# ---------------------------------------------------------------------------
def test_load_state_no_file(tmp_path: Path):
    plugin = make_plugin()
    plugin._state_path = tmp_path / "nonexistent.json"
    state = plugin._load_state()
    assert state["initialized"] is False
    assert state["seen_post_uuids"] == []
    assert "player_alert_state" in state


# ---------------------------------------------------------------------------
# _load_state – valid state
# ---------------------------------------------------------------------------
def test_load_state_valid(tmp_path: Path):
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps({"initialized": True, "seen_post_uuids": ["a", "b", "c"]})
    )
    plugin = make_plugin()
    plugin._state_path = state_file
    state = plugin._load_state()
    assert state["initialized"] is True
    assert state["seen_post_uuids"] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# _load_state – corrupted JSON → default
# ---------------------------------------------------------------------------
def test_load_state_corrupted(caplog, tmp_path: Path):
    caplog.set_level(logging.WARNING)
    state_file = tmp_path / "state.json"
    state_file.write_text("not json{{")
    plugin = make_plugin()
    plugin._state_path = state_file
    state = plugin._load_state()
    assert state["initialized"] is False
    assert state["seen_post_uuids"] == []
    assert "player_alert_state" in state
    assert "状态文件读取失败" in caplog.text


# ---------------------------------------------------------------------------
# _load_state – root not dict
# ---------------------------------------------------------------------------
def test_load_state_root_not_dict(caplog, tmp_path: Path):
    caplog.set_level(logging.WARNING)
    state_file = tmp_path / "state.json"
    state_file.write_text("[1, 2, 3]")
    plugin = make_plugin()
    plugin._state_path = state_file
    state = plugin._load_state()
    assert state["initialized"] is False
    assert state["seen_post_uuids"] == []
    assert "player_alert_state" in state
    assert state["player_alert_state"] is not None


# ---------------------------------------------------------------------------
# _save_state – writes valid JSON
# ---------------------------------------------------------------------------
def test_save_state(tmp_path: Path):
    state_file = tmp_path / "subdir" / "state.json"
    plugin = make_plugin()
    plugin._state_path = state_file
    plugin._state = {"initialized": True, "seen_post_uuids": ["x", "y"]}
    plugin._save_state()

    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert data["initialized"] is True
    assert data["seen_post_uuids"] == ["x", "y"]


# ---------------------------------------------------------------------------
# _save_state – _state_path is None → no-op
# ---------------------------------------------------------------------------
def test_save_state_no_path():
    plugin = make_plugin()
    plugin._state_path = None
    plugin._state = {"initialized": True, "seen_post_uuids": []}
    # should not raise
    plugin._save_state()


# ---------------------------------------------------------------------------
# _mark_seen – deduplicates, moves to end, caps at MAX
# ---------------------------------------------------------------------------
def test_mark_seen_dedup_and_cap():
    plugin = make_plugin()
    plugin._state["seen_post_uuids"] = ["a", "b", "c"]

    plugin._mark_seen(["b", "d"])
    # b moves to end, d appended
    assert plugin._state["seen_post_uuids"] == ["a", "c", "b", "d"]

    plugin._mark_seen(["e"])
    assert plugin._state["seen_post_uuids"] == ["a", "c", "b", "d", "e"]


# ---------------------------------------------------------------------------
# _mark_seen – respects MAX_SEEN_POSTS (500 by default → test with smaller)
# ---------------------------------------------------------------------------
def test_mark_seen_cap(monkeypatch):
    monkeypatch.setattr("core.state_store.MAX_SEEN_POSTS", 3)
    plugin = make_plugin()
    plugin._state["seen_post_uuids"] = ["a", "b", "c"]

    plugin._mark_seen(["d"])
    assert plugin._state["seen_post_uuids"] == ["b", "c", "d"]
