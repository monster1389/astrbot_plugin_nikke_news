"""Chromium 浏览器上下文管理器：统一 Playwright 启动与关闭。"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from core.utils import parse_cookie_pairs


class BrowserLaunchError(Exception):
    """Playwright 不可用或浏览器启动失败。"""


def parse_cookie_header(cookie_header: str) -> list[dict[str, object]]:
    """解析 Cookie 头字符串为 Playwright cookie 对象列表。

    Args:
        cookie_header: 完整的 Cookie 头字符串。

    Returns:
        Playwright cookie 对象列表，每个元素含 name、value、domain 等字段。
    """
    cookies: list[dict[str, object]] = []
    for name, value in parse_cookie_pairs(cookie_header):
        for domain in (".blablalink.com", "www.blablalink.com"):
            cookies.append(
                {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": "/",
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "Lax",
                }
            )
    return cookies


@asynccontextmanager
async def browser_context(
    *,
    cookie_header: str = "",
    language: str = "en",
    viewport: dict[str, int] | None = None,
    extra_http_headers: dict[str, str] | None = None,
) -> AsyncIterator:
    """启动 Chromium 并返回 Page，退出时自动关闭浏览器。

    只负责 launch → context → page 创建和 browser.close()。
    page.goto / response handler 等业务逻辑由调用方处理。

    Args:
        cookie_header: Cookie 请求头字符串，空串表示无 Cookie。
        language: new_context 的 locale 参数。
        viewport: 视口尺寸，None 使用默认。
        extra_http_headers: new_context 的 extra_http_headers。

    Yields:
        Playwright Page 对象。

    Raises:
        BrowserLaunchError: Playwright 导入失败。
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise BrowserLaunchError("当前环境未安装 Playwright。") from exc

    context_kwargs: dict[str, object] = {"locale": language}
    if viewport is not None:
        context_kwargs["viewport"] = viewport
    if extra_http_headers is not None:
        context_kwargs["extra_http_headers"] = extra_http_headers

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(**context_kwargs)
            if cookie_header:
                cookies = parse_cookie_header(cookie_header)
                if cookies:
                    await ctx.add_cookies(cookies)
            page = await ctx.new_page()
            yield page
        finally:
            await browser.close()
