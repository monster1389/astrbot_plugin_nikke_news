"""CDN 响应采集原语：拦截 Playwright 网络响应并按需让出事件循环。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from astrbot.api import logger

if TYPE_CHECKING:
    from playwright.async_api import Response


class CdnResponseCollector:
    """拦截 Playwright 网络响应，按需让出事件循环，逐个吐出解析后的 JSON。

    只负责机制：注册拦截 → 维护 pending 队列 → 队列空时 wait_for_timeout 让出
    → pop + json() 解析。停止时机、stall 计数、业务判定全由调用方决定。

    Attributes:
        _page: Playwright Page 实例。
        _url_filter: 判定响应 URL 是否感兴趣的谓词。
        _wait_ms: 队列空时等待的毫秒数。
        _pending: 待处理的响应队列。
    """

    def __init__(
        self,
        page,
        *,
        url_filter: Callable[[str], bool],
        wait_ms: int = 200,
    ):
        self._page = page
        self._url_filter = url_filter
        self._wait_ms = wait_ms
        self._pending: list = []
        page.on("response", self._on_response)

    def _on_response(self, response) -> None:
        if self._url_filter(response.url):
            self._pending.append(response)

    async def next(self) -> tuple[Response, Any] | None:
        """返回下一个匹配响应 (response, 解析后 JSON)，队列空时让出后返回 None。

        Returns:
            (response, 解析后 JSON) 元组；当前无就绪响应时返回 None（表示空转一拍）。
        """
        while self._pending:
            response = self._pending.pop(0)
            try:
                return response, await response.json()
            except Exception:
                logger.debug("NIKKE CDN JSON 解析失败", exc_info=True)
        await self._page.wait_for_timeout(self._wait_ms)
        return None
