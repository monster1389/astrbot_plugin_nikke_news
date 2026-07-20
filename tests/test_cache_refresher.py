# tests/test_cache_refresher.py
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.cache_refresher import CacheRefresher
from core.cookie_status import CookieStatus


@pytest.fixture
def mock_services(monkeypatch):
    char_svc = MagicMock()
    char_svc.refresh_mappings = AsyncMock(
        return_value=(
            "英文映射已刷新：角色 122 个，词条 3 个。\n已重载本地角色列表，共 122 个角色。",
            False,
        )
    )

    avatar_svc = MagicMock()
    avatar_svc.refresh_cached = AsyncMock(
        return_value=("头像缓存刷新完成：已缓存 50 个，下载完成 0 个。（12s）", False)
    )

    player_poller = MagicMock()
    player_poller.cookie_status = MagicMock(return_value=CookieStatus.AVAILABLE)

    config = MagicMock()
    config.player_data_cookie = MagicMock(return_value="ck=abc")

    # mock playwright import — CacheRefresher 用 _browser=None 降级
    import builtins

    _real_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "playwright.async_api":
            raise ImportError("no playwright")
        return _real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)

    return char_svc, avatar_svc, player_poller, config


class TestCacheRefresher:
    def test_refresh_concurrent(self, mock_services):
        char_svc, avatar_svc, player_poller, config = mock_services
        cr = CacheRefresher(char_svc, avatar_svc, player_poller, config)
        msg, char_failed, avatar_failed = asyncio.run(cr.refresh(force=True))
        assert char_failed is False
        assert avatar_failed is False
        assert "英文映射已刷新" in msg
        assert "头像缓存刷新完成" in msg
        assert "总耗时" in msg
        char_svc.refresh_mappings.assert_called_once_with(force=True, _browser=None)
        avatar_svc.refresh_cached.assert_called_once_with(
            "ck=abc", force=True, _browser=None
        )

    def test_returns_none_when_cookie_unavailable(self, mock_services):
        char_svc, avatar_svc, player_poller, config = mock_services
        player_poller.cookie_status.return_value = CookieStatus.EMPTY
        cr = CacheRefresher(char_svc, avatar_svc, player_poller, config)
        result = asyncio.run(cr.refresh())
        assert result is None
        char_svc.refresh_mappings.assert_not_called()

    def test_returns_none_on_concurrent_call(self, mock_services):
        char_svc, avatar_svc, player_poller, config = mock_services
        cr = CacheRefresher(char_svc, avatar_svc, player_poller, config)
        cr._in_progress = True
        result = asyncio.run(cr.refresh())
        assert result is None

    def test_handles_refresh_exception(self, mock_services):
        char_svc, avatar_svc, player_poller, config = mock_services
        char_svc.refresh_mappings = AsyncMock(
            side_effect=RuntimeError("Playwright crash")
        )
        cr = CacheRefresher(char_svc, avatar_svc, player_poller, config)
        msg, char_failed, avatar_failed = asyncio.run(cr.refresh(force=True))
        assert char_failed is True
        assert avatar_failed is False
        assert "角色映射刷新失败" in msg
        assert "头像缓存刷新完成" in msg

    def test_skip_character_and_avatar(self, mock_services):
        char_svc, avatar_svc, player_poller, config = mock_services
        cr = CacheRefresher(char_svc, avatar_svc, player_poller, config)
        msg, char_failed, avatar_failed = asyncio.run(
            cr.refresh(skip_character=True, skip_avatar=True)
        )
        assert char_failed is False
        assert avatar_failed is False
        assert "总耗时" in msg
        char_svc.refresh_mappings.assert_not_called()
        avatar_svc.refresh_cached.assert_not_called()

    def test_failure_adds_reset_hint_when_not_force(self, mock_services):
        char_svc, avatar_svc, player_poller, config = mock_services
        char_svc.refresh_mappings = AsyncMock(side_effect=RuntimeError("crash"))
        cr = CacheRefresher(char_svc, avatar_svc, player_poller, config)
        msg, char_failed, avatar_failed = asyncio.run(cr.refresh(force=False))
        assert char_failed is True
        assert "请执行 /nikke_refresh 重置失败状态后重试。" in msg

    def test_failure_no_reset_hint_when_force(self, mock_services):
        char_svc, avatar_svc, player_poller, config = mock_services
        char_svc.refresh_mappings = AsyncMock(side_effect=RuntimeError("crash"))
        cr = CacheRefresher(char_svc, avatar_svc, player_poller, config)
        msg, char_failed, avatar_failed = asyncio.run(cr.refresh(force=True))
        assert char_failed is True
        assert "请执行 /nikke_refresh 重置失败状态后重试。" not in msg
