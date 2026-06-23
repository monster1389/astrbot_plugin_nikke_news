# tests/test_cache_refresher.py
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.cache_refresher import CacheRefresher
from core.cookie_status import CookieStatus


@pytest.fixture
def mock_services():
    char_svc = MagicMock()
    char_svc.refresh_mappings = AsyncMock(
        return_value="英文映射已刷新：角色 122 个，词条 3 个。（18s）"
    )

    avatar_svc = MagicMock()
    avatar_svc.refresh_cached = AsyncMock(
        return_value="头像缓存刷新完成：已缓存 50 个，下载完成 0 个。（12s）"
    )

    player_poller = MagicMock()
    player_poller.cookie_status = MagicMock(return_value=CookieStatus.AVAILABLE)

    config = MagicMock()
    config.player_data_cookie = MagicMock(return_value="ck=abc")

    return char_svc, avatar_svc, player_poller, config


class TestCacheRefresher:
    def test_refresh_concurrent(self, mock_services):
        char_svc, avatar_svc, player_poller, config = mock_services
        cr = CacheRefresher(char_svc, avatar_svc, player_poller, config)
        msg = asyncio.run(cr.refresh(force=True))
        assert "英文映射已刷新" in msg
        assert "头像缓存刷新完成" in msg
        assert "总耗时" in msg
        char_svc.refresh_mappings.assert_called_once_with(force=True)
        avatar_svc.refresh_cached.assert_called_once_with("ck=abc")

    def test_returns_none_when_cookie_unavailable(self, mock_services):
        char_svc, avatar_svc, player_poller, config = mock_services
        player_poller.cookie_status.return_value = CookieStatus.EMPTY
        cr = CacheRefresher(char_svc, avatar_svc, player_poller, config)
        msg = asyncio.run(cr.refresh())
        assert msg is None
        char_svc.refresh_mappings.assert_not_called()

    def test_returns_none_on_concurrent_call(self, mock_services):
        char_svc, avatar_svc, player_poller, config = mock_services
        cr = CacheRefresher(char_svc, avatar_svc, player_poller, config)
        cr._in_progress = True
        msg = asyncio.run(cr.refresh())
        assert msg is None

    def test_handles_refresh_exception(self, mock_services):
        char_svc, avatar_svc, player_poller, config = mock_services
        char_svc.refresh_mappings = AsyncMock(
            side_effect=RuntimeError("Playwright crash")
        )
        cr = CacheRefresher(char_svc, avatar_svc, player_poller, config)
        msg = asyncio.run(cr.refresh(force=True))
        assert "角色映射刷新失败" in msg
        assert "头像缓存刷新完成" in msg
