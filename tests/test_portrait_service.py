import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from player.portrait_service import PortraitMappingCache, PortraitService


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
    async def test_overwrites_existing(self, service):
        (service._portraits_dir / "101.webp").write_bytes(b"cached")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content = b"fresh_data"
        service._client.get.return_value = mock_resp

        new_count = await service._download_mappings(
            {101: "https://cdn.example.com/101.webp"}
        )

        assert new_count == 1
        assert service.portrait_path(101).read_bytes() == b"fresh_data"

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


# ── PortraitMappingCache ──────────────────────────────────────────


def test_cache_save_and_load(tmp_path):
    cache_path = tmp_path / "portrait_mappings.json"
    cache = PortraitMappingCache(cache_path)

    mappings = {5005: "https://sg-tools-cdn.blablalink.com/foo/bar.webp"}
    cache.save(mappings)

    loaded = cache.load()
    assert loaded == mappings


def test_cache_load_missing_file():
    cache = PortraitMappingCache(Path("/nonexistent/portrait_mappings.json"))
    assert cache.load() == {}


def test_cache_is_stale_fresh(tmp_path):
    cache_path = tmp_path / "portrait_mappings.json"
    cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "mappings": {"5005": "https://example.com/a.webp"},
            }
        )
    )
    cache = PortraitMappingCache(cache_path)
    assert cache.is_stale() is False


def test_cache_is_stale_expired(tmp_path):
    cache_path = tmp_path / "portrait_mappings.json"
    cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": (
                    datetime.now(timezone.utc) - timedelta(hours=200)
                ).isoformat(),
                "mappings": {"5005": "https://example.com/a.webp"},
            }
        )
    )
    cache = PortraitMappingCache(cache_path)
    assert cache.is_stale() is True


def test_cache_is_stale_no_file():
    cache = PortraitMappingCache(Path("/nonexistent/portrait_mappings.json"))
    assert cache.is_stale() is True


def test_cache_load_wrong_version(tmp_path):
    cache_path = tmp_path / "portrait_mappings.json"
    cache_path.write_text(
        json.dumps(
            {
                "version": 99,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "mappings": {"5005": "https://example.com/a.webp"},
            }
        )
    )
    cache = PortraitMappingCache(cache_path)
    assert cache.load() == {}


def test_cache_save_creates_parent_dir(tmp_path):
    cache_path = tmp_path / "subdir" / "portrait_mappings.json"
    cache = PortraitMappingCache(cache_path)
    cache.save({5005: "https://example.com/a.webp"})
    assert cache_path.exists()
