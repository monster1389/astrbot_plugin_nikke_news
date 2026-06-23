# tests/test_cookie_status.py
import pytest
from core.cookie_status import CookieStatus
from core.config import PluginConfig
from player.player_poller import PlayerPoller


def _make_poller(**kwargs):
    config_data = {
        "新闻": {"enabled": True},
        "玩家": {
            "cookie": kwargs.get("cookie", "ck=abc"),
            "状态提醒": {"enabled": kwargs.get("enabled", True)},
        },
    }
    config = PluginConfig(config_data)
    state = {}
    if kwargs.get("cookie_invalid"):
        state["player_alert_state"] = {"cookie_invalid_notified": True}
    return PlayerPoller(client=None, config=config, state=state, save_state=lambda: None)


class TestCookieStatus:
    def test_available(self):
        poller = _make_poller(enabled=True, cookie="ck=abc")
        assert poller.cookie_status() == CookieStatus.AVAILABLE

    def test_disabled(self):
        poller = _make_poller(enabled=False)
        assert poller.cookie_status() == CookieStatus.DISABLED

    def test_empty_cookie(self):
        poller = _make_poller(enabled=True, cookie="")
        assert poller.cookie_status() == CookieStatus.EMPTY

    def test_invalid(self):
        poller = _make_poller(enabled=True, cookie="ck=abc", cookie_invalid=True)
        assert poller.cookie_status() == CookieStatus.INVALID
