"""CdnResponseCollector 机制原语测试。"""

import pytest

from core.cdn_collector import CdnResponseCollector


class FakePage:
    """模拟 Playwright Page 的 on / wait_for_timeout。"""

    def __init__(self):
        self._handler = None
        self.wait_calls: list[int] = []

    def on(self, event: str, handler):
        self._handler = handler

    def emit(self, response) -> None:
        """模拟响应到达，触发已注册的拦截回调。"""
        self._handler(response)

    async def wait_for_timeout(self, ms: int) -> None:
        self.wait_calls.append(ms)


class FakeResponse:
    """模拟 Playwright Response 的 url / json。"""

    def __init__(self, url: str, data=None, error: Exception | None = None):
        self.url = url
        self._data = data
        self._error = error

    async def json(self):
        if self._error is not None:
            raise self._error
        return self._data


@pytest.mark.asyncio
async def test_returns_matching_response():
    page = FakePage()
    collector = CdnResponseCollector(page, url_filter=lambda u: u.endswith(".json"))
    resp = FakeResponse("https://cdn/x.json", {"name_code": 1})
    page.emit(resp)

    result = await collector.next()

    assert result[0] is resp
    assert result[1] == {"name_code": 1}


@pytest.mark.asyncio
async def test_skips_non_matching_url():
    page = FakePage()
    collector = CdnResponseCollector(page, url_filter=lambda u: u.endswith(".json"))
    page.emit(FakeResponse("https://cdn/x.html", {"a": 1}))

    assert await collector.next() is None
    assert page.wait_calls == [200]


@pytest.mark.asyncio
async def test_skips_bad_json():
    page = FakePage()
    collector = CdnResponseCollector(page, url_filter=lambda u: True)
    page.emit(FakeResponse("https://cdn/bad.json", error=ValueError("boom")))
    page.emit(FakeResponse("https://cdn/good.json", {"ok": 1}))

    result = await collector.next()

    assert result[1] == {"ok": 1}


@pytest.mark.asyncio
async def test_returns_none_when_empty():
    page = FakePage()
    collector = CdnResponseCollector(page, url_filter=lambda u: True)

    assert await collector.next() is None
    assert page.wait_calls == [200]


@pytest.mark.asyncio
async def test_pops_in_fifo_order():
    page = FakePage()
    collector = CdnResponseCollector(page, url_filter=lambda u: True)
    page.emit(FakeResponse("https://cdn/1.json", {"n": 1}))
    page.emit(FakeResponse("https://cdn/2.json", {"n": 2}))

    assert (await collector.next())[1] == {"n": 1}
    assert (await collector.next())[1] == {"n": 2}
