"""launch_browser 原语测试。"""

import builtins
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.browser_context import BrowserLaunchError, launch_browser


@pytest.mark.asyncio
async def test_raises_on_import_error(monkeypatch):
    real_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "playwright.async_api":
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)

    with pytest.raises(BrowserLaunchError):
        async with launch_browser():
            pass


@pytest.mark.asyncio
async def test_yields_browser_and_closes(monkeypatch):
    browser = MagicMock()
    browser.close = AsyncMock()

    fake_pw = MagicMock()
    fake_pw.chromium.launch = AsyncMock(return_value=browser)
    async_playwright_cm = MagicMock()
    async_playwright_cm.__aenter__ = AsyncMock(return_value=fake_pw)
    async_playwright_cm.__aexit__ = AsyncMock(return_value=None)
    async_playwright = MagicMock(return_value=async_playwright_cm)

    fake_module = types.ModuleType("playwright.async_api")
    fake_module.async_playwright = async_playwright
    monkeypatch.setitem(sys.modules, "playwright.async_api", fake_module)

    async with launch_browser() as got:
        assert got is browser

    fake_pw.chromium.launch.assert_awaited_once_with(headless=True)
    browser.close.assert_awaited_once()
