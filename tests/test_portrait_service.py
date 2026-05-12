from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from player.portrait_service import PortraitService


@pytest.fixture
def service(tmp_path):
    client = MagicMock(spec=httpx.AsyncClient)
    client.get = AsyncMock()
    return PortraitService(tmp_path, client)


class TestPortraitPath:
    def test_portrait_path(self, service):
        assert service.portrait_path(101) == service._portraits_dir / "101.webp"

    def test_exists_true(self, service):
        (service._portraits_dir / "101.webp").write_bytes(b"fake")
        assert service.exists(101) is True

    def test_exists_false(self, service):
        assert service.exists(999) is False


class TestCachedCount:
    def test_empty(self, service):
        assert service.cached_count() == 0

    def test_nonempty(self, service):
        (service._portraits_dir / "101.webp").write_bytes(b"a")
        (service._portraits_dir / "102.webp").write_bytes(b"b")
        assert service.cached_count() == 2


class TestDownloadMappings:
    @pytest.mark.asyncio
    async def test_downloads_new_files(self, service):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content = b"image_data"
        service._client.get.return_value = mock_resp

        new_count = await service._download_mappings(
            {101: "https://cdn.example.com/101.webp"}
        )

        assert new_count == 1
        assert service.exists(101)
        assert service.portrait_path(101).read_bytes() == b"image_data"

    @pytest.mark.asyncio
    async def test_skips_existing(self, service):
        (service._portraits_dir / "101.webp").write_bytes(b"cached")

        new_count = await service._download_mappings(
            {101: "https://cdn.example.com/101.webp"}
        )

        assert new_count == 0
        service._client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_download_failure_continues(self, service):
        service._client.get.side_effect = Exception("network error")

        new_count = await service._download_mappings(
            {101: "https://cdn.example.com/101.webp"}
        )

        assert new_count == 0
        assert not service.exists(101)


class TestScrapeMappings:
    @pytest.mark.asyncio
    async def test_playwright_missing_returns_empty(self, service, monkeypatch):
        import builtins

        _real_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "playwright.async_api":
                raise ImportError("no playwright")
            return _real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _mock_import)

        result = await service._scrape_portrait_mappings("cookie=test")
        assert result == {}
