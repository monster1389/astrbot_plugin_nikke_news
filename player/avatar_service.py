import time
from pathlib import Path

import httpx
from astrbot.api import logger

from player.avatar_mapping_cache import AvatarMappingCache
from player.avatar_scraper import AvatarScraper


class AvatarService:
    """角色头像管理：从 Blablalink CDN 抓取并缓存头像图片。"""

    def __init__(self, data_dir: Path, client: httpx.AsyncClient):
        self._client = client
        self._mapping_cache = AvatarMappingCache(data_dir / "avatar_mappings.json")
        self._scraper = AvatarScraper(self._mapping_cache)
        try:
            self._avatars_dir = data_dir / "avatars"
            self._avatars_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning(f"NIKKE 头像目录创建失败：{exc}", exc_info=True)
            self._avatars_dir = None

    def avatar_path(self, name_code: int) -> Path | None:
        if not self._avatars_dir:
            return None
        return self._avatars_dir / f"{name_code}.webp"

    def exists(self, name_code: int) -> bool:
        path = self.avatar_path(name_code)
        return path.exists() if path else False

    def cached_count(self) -> int:
        if not self._avatars_dir:
            return 0
        return len(list(self._avatars_dir.glob("*.webp")))

    async def refresh_all(self, cookie: str) -> str:
        """抓取并下载所有角色头像缓存（/nikke_avatar_all）。"""
        t0 = time.monotonic()
        mappings = await self._scraper.scrape(cookie)
        if not mappings:
            return (
                "未获取到角色头像映射。请确认：\n"
                "1. Cookie 是否有效\n"
                "2. 当前环境是否安装了 Playwright"
            )
        new_count = await self._download_mappings(mappings)
        elapsed = time.monotonic() - t0
        return (
            f"头像缓存刷新完成：共 {len(mappings)} 个角色，"
            f"下载完成 {new_count} 个（耗时 {elapsed:.0f}s）。"
        )

    async def refresh_cached(self, cookie: str) -> str:
        """抓取头像映射并仅重新下载本地已有缓存文件的头像。"""
        t0 = time.monotonic()
        mappings = await self._scraper.scrape(cookie)
        if not mappings:
            return (
                "未获取到角色头像映射。请确认：\n"
                "1. Cookie 是否有效\n"
                "2. 当前环境是否安装了 Playwright"
            )
        cached = {code: url for code, url in mappings.items() if self.exists(code)}
        if not cached:
            elapsed = time.monotonic() - t0
            return (
                f"头像映射已更新（共 {len(mappings)} 个角色），"
                f"但本地无已缓存头像，未下载任何文件（耗时 {elapsed:.0f}s）。"
            )
        new_count = await self._download_mappings(cached)
        elapsed = time.monotonic() - t0
        return (
            f"头像缓存刷新完成：映射共 {len(mappings)} 个角色，"
            f"已缓存 {len(cached)} 个，下载完成 {new_count} 个（耗时 {elapsed:.0f}s）。"
        )

    def _load_mappings(self) -> dict[int, str]:
        """加载映射：优先磁盘缓存（未过期），否则返回空。"""
        if self._mapping_cache.is_stale():
            return {}
        return self._mapping_cache.load()

    async def ensure_avatar(self, name_code: int, cookie: str) -> bool:
        """按需下载单个角色头像。先查磁盘缓存 → 过期则 Playwright 抓取 → 下载。"""
        if self.exists(name_code):
            return True

        mappings = self._load_mappings()
        if not mappings:
            mappings = await self._scraper.scrape(cookie)
        url = mappings.get(name_code)
        if not url:
            return False

        return await self._download_one(name_code, url)

    async def _download_one(self, name_code: int, url: str) -> bool:
        """下载单个角色头像到本地 avatars/ 目录。"""
        if self._avatars_dir:
            self._avatars_dir.mkdir(parents=True, exist_ok=True)
        path = self.avatar_path(name_code)
        if path is None:
            return False
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            path.write_bytes(resp.content)
            return True
        except Exception as exc:
            logger.warning(
                f"NIKKE 头像下载失败 {name_code} ({url}): {exc}", exc_info=True
            )
            return False

    async def _download_mappings(self, mappings: dict[int, str]) -> int:
        """批量下载角色头像图片到本地 avatars/ 目录。"""
        if self._avatars_dir:
            self._avatars_dir.mkdir(parents=True, exist_ok=True)
        new_count = 0
        for name_code, url in mappings.items():
            if await self._download_one(name_code, url):
                new_count += 1
        if new_count:
            logger.info(f"NIKKE 头像下载完成：{new_count} 个。")
        return new_count
