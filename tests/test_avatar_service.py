import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from player.avatar_mapping_cache import AvatarMappingCache
from player.avatar_service import AvatarService


@pytest.fixture
def service(tmp_path):
    client = MagicMock(spec=httpx.AsyncClient)
    client.get = AsyncMock()
    return AvatarService(tmp_path, client, ttl_hours=168)


class TestAvatarPath:
    def test_avatar_path(self, service):
        assert service.avatar_path(101) == service._avatars_dir / "101.webp"

    def test_exists_true(self, service):
        (service._avatars_dir / "101.webp").write_bytes(b"fake")
        assert service.exists(101) is True

    def test_exists_false(self, service):
        assert service.exists(999) is False

    def test_is_mapping_stale_no_cache(self, service):
        assert service.is_mapping_stale() is True

    def test_is_mapping_stale_fresh(self, service, tmp_path):
        cache_path = tmp_path / "avatar_mappings.json"
        cache_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "mappings": {"5005": "https://example.com/a.webp"},
                }
            )
        )
        cache_path.chmod(0o666)
        assert service.is_mapping_stale() is False


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
        assert service.avatar_path(101).read_bytes() == b"image_data"

    @pytest.mark.asyncio
    async def test_overwrites_existing(self, service):
        (service._avatars_dir / "101.webp").write_bytes(b"cached")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content = b"fresh_data"
        service._client.get.return_value = mock_resp

        new_count = await service._download_mappings(
            {101: "https://cdn.example.com/101.webp"}
        )

        assert new_count == 1
        assert service.avatar_path(101).read_bytes() == b"fresh_data"

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

        result = await service._scraper.scrape("cookie=test")
        assert result == {}


class TestRefreshCached:
    @pytest.mark.asyncio
    async def test_refresh_cached_only_downloads_existing(self, service, monkeypatch):
        # Pre-create a cached file for 101 only
        (service._avatars_dir / "101.webp").write_bytes(b"cached")

        mock_mappings = {
            101: "https://cdn.example.com/101.webp",
            102: "https://cdn.example.com/102.webp",
        }
        called_with = []

        async def fake_scrape(cookie, _browser=None):
            return mock_mappings

        async def fake_download(mappings):
            called_with.append(dict(mappings))
            return len(mappings)

        monkeypatch.setattr(service._scraper, "scrape", fake_scrape)
        monkeypatch.setattr(service, "_download_mappings", fake_download)

        msg, failed = await service.refresh_cached("test_cookie")

        assert failed is False
        assert called_with == [{101: "https://cdn.example.com/101.webp"}]
        assert "已缓存 1 个" in msg

    @pytest.mark.asyncio
    async def test_refresh_cached_no_local_files(self, service, monkeypatch):
        mock_mappings = {101: "https://cdn.example.com/101.webp"}

        async def fake_scrape(cookie, _browser=None):
            return mock_mappings

        monkeypatch.setattr(service._scraper, "scrape", fake_scrape)

        msg, failed = await service.refresh_cached("test_cookie")
        assert failed is False
        assert "未下载任何文件" in msg

    @pytest.mark.asyncio
    async def test_refresh_cached_scrape_returns_empty(self, service, monkeypatch):
        async def fake_scrape(cookie, _browser=None):
            return {}

        monkeypatch.setattr(service._scraper, "scrape", fake_scrape)

        msg, failed = await service.refresh_cached("test_cookie")
        assert failed is True
        assert "未获取到角色头像映射" in msg

    @pytest.mark.asyncio
    async def test_refresh_cached_skips_when_fresh(
        self, service, monkeypatch, tmp_path
    ):
        """TTL 未过期时返回空串且不抓取。"""
        cache_path = tmp_path / "avatar_mappings.json"
        cache_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "mappings": {"5005": "https://example.com/a.webp"},
                }
            )
        )
        scrape_called = False

        async def fake_scrape(cookie, _browser=None):
            nonlocal scrape_called
            scrape_called = True
            return {}

        monkeypatch.setattr(service._scraper, "scrape", fake_scrape)

        msg, failed = await service.refresh_cached("test_cookie")
        assert (msg, failed) == ("", False)
        assert scrape_called is False

    @pytest.mark.asyncio
    async def test_refresh_cached_force_bypasses_ttl(self, service, monkeypatch):
        """force=True 时跳过 TTL 检查直接抓取。"""
        scrape_called = False

        async def fake_scrape(cookie, _browser=None):
            nonlocal scrape_called
            scrape_called = True
            return {}

        monkeypatch.setattr(service._scraper, "scrape", fake_scrape)

        msg, failed = await service.refresh_cached("test_cookie", force=True)
        assert failed is True
        assert scrape_called is True


class TestAvatarHint:
    def test_no_cookie(self, service):
        assert service.avatar_hint(101, "") is None

    def test_exists(self, service):
        (service._avatars_dir / "101.webp").write_bytes(b"fake")
        assert service.avatar_hint(101, "cookie") is None

    def test_fresh_mapping(self, service, tmp_path):
        (tmp_path / "avatar_mappings.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "mappings": {"5005": "https://example.com/a.webp"},
                }
            )
        )
        assert service.avatar_hint(101, "cookie") is None

    def test_stale_returns_hint(self, service):
        assert service.avatar_hint(101, "cookie") == "正在刷新头像映射（约 20-30s）..."


class TestEnsureAvatarPath:
    @pytest.mark.asyncio
    async def test_no_cookie(self, service):
        assert await service.ensure_avatar_path(101, "") is None

    @pytest.mark.asyncio
    async def test_exists(self, service):
        (service._avatars_dir / "101.webp").write_bytes(b"fake")
        path = await service.ensure_avatar_path(101, "cookie")
        assert path == service._avatars_dir / "101.webp"

    @pytest.mark.asyncio
    async def test_downloads(self, service, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content = b"image_data"
        service._client.get.return_value = mock_resp

        async def fake_scrape(cookie, _browser=None):
            return {101: "https://cdn.example.com/101.webp"}

        monkeypatch.setattr(service._scraper, "scrape", fake_scrape)

        path = await service.ensure_avatar_path(101, "cookie")
        assert path == service._avatars_dir / "101.webp"
        assert path.read_bytes() == b"image_data"

    @pytest.mark.asyncio
    async def test_download_fails(self, service, monkeypatch):
        async def fake_scrape(cookie, _browser=None):
            return {}

        monkeypatch.setattr(service._scraper, "scrape", fake_scrape)

        assert await service.ensure_avatar_path(101, "cookie") is None


# ── AvatarMappingCache ──────────────────────────────────────────


def test_cache_save_and_load(tmp_path):
    cache_path = tmp_path / "avatar_mappings.json"
    cache = AvatarMappingCache(cache_path)

    mappings = {5005: "https://sg-tools-cdn.blablalink.com/foo/bar.webp"}
    cache.save(mappings)

    loaded = cache.load()
    assert loaded == mappings


def test_cache_load_missing_file():
    cache = AvatarMappingCache(Path("/nonexistent/avatar_mappings.json"))
    assert cache.load() == {}


def test_cache_is_stale_fresh(tmp_path):
    cache_path = tmp_path / "avatar_mappings.json"
    cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "mappings": {"5005": "https://example.com/a.webp"},
            }
        )
    )
    ttl = 168
    cache = AvatarMappingCache(cache_path)
    assert cache.is_stale(ttl) is False


def test_cache_is_stale_expired(tmp_path):
    cache_path = tmp_path / "avatar_mappings.json"
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
    ttl = 168
    cache = AvatarMappingCache(cache_path)
    assert cache.is_stale(ttl) is True


def test_cache_is_stale_no_file():
    cache = AvatarMappingCache(Path("/nonexistent/avatar_mappings.json"))
    assert cache.is_stale(168) is True


def test_cache_load_wrong_version(tmp_path):
    cache_path = tmp_path / "avatar_mappings.json"
    cache_path.write_text(
        json.dumps(
            {
                "version": 99,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "mappings": {"5005": "https://example.com/a.webp"},
            }
        )
    )
    cache = AvatarMappingCache(cache_path)
    assert cache.load() == {}


def test_cache_save_creates_parent_dir(tmp_path):
    cache_path = tmp_path / "subdir" / "avatar_mappings.json"
    cache = AvatarMappingCache(cache_path)
    cache.save({5005: "https://example.com/a.webp"})
    assert cache_path.exists()
