from pathlib import Path

import httpx
from astrbot.api import logger

from player.player_mapping_refresher import parse_cookie_header

SHIFTYSPAD_COMBAT_URL = "https://www.blablalink.com/shiftyspad/nikke-list?type=combat"


class PortraitService:
    """角色头像管理：从 Blablalink CDN 抓取并缓存头像图片。"""

    def __init__(self, data_dir: Path, client: httpx.AsyncClient):
        self._client = client
        try:
            self._portraits_dir = data_dir / "portraits"
            self._portraits_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning(f"NIKKE 头像目录创建失败：{exc}", exc_info=True)
            self._portraits_dir = None

    def portrait_path(self, name_code: int) -> Path | None:
        if not self._portraits_dir:
            return None
        return self._portraits_dir / f"{name_code}.webp"

    def exists(self, name_code: int) -> bool:
        path = self.portrait_path(name_code)
        return path.exists() if path else False

    def cached_count(self) -> int:
        if not self._portraits_dir:
            return 0
        return len(list(self._portraits_dir.glob("*.webp")))

    async def refresh_all(self, cookie: str) -> str:
        """抓取并下载所有角色头像缓存（/nikke_portrait_refresh）。"""
        mappings = await self._scrape_portrait_mappings(cookie)
        if not mappings:
            return (
                "未获取到角色头像映射。请确认：\n"
                "1. Cookie 是否有效\n"
                "2. 当前环境是否安装了 Playwright"
            )
        new_count = await self._download_mappings(mappings)
        return f"头像缓存刷新完成：共 {len(mappings)} 个角色，下载完成 {new_count} 个。"

    async def refresh_first_n(self, n: int, cookie: str) -> str:
        """启动时预缓存前 N 个角色头像。"""
        mappings = await self._scrape_portrait_mappings(cookie)
        if not mappings:
            return "未获取到角色头像映射（Cookie 或 Playwright 问题，详见日志）。"
        first_n = dict(list(mappings.items())[:n])
        new_count = await self._download_mappings(first_n)
        return f"初始头像缓存完成：已缓存前 {n} 个角色，下载完成 {new_count} 个。"

    async def _scrape_portrait_mappings(self, cookie: str) -> dict[int, str]:
        """用 Playwright 打开角色列表页，在初始渲染窗口提取 name_code→图片 URL 映射。"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("NIKKE 头像抓取需要 Playwright，当前环境未安装。")
            return {}

        logger.info("NIKKE Chromium 头像映射抓取启动...")
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        locale="zh-TW",
                        viewport={"width": 1280, "height": 900},
                    )
                    cookies = parse_cookie_header(cookie)
                    if cookies:
                        await context.add_cookies(cookies)
                    page = await context.new_page()

                    await page.goto(
                        SHIFTYSPAD_COMBAT_URL, wait_until="load", timeout=60000
                    )

                    # 页面加载后约 4-5 秒会短暂渲染全部卡片（含 CDN 图片 URL），
                    # 之后虚拟列表 reset 只剩视口内 ~10 张。在此窗口内轮询抓取。
                    mappings: dict[int, str] = {}
                    for _ in range(50):
                        await page.wait_for_timeout(200)
                        result = await page.evaluate("""() => {
                            const cards = document.querySelectorAll('[data-cname="card-item"]');
                            if (cards.length < 50) return null;
                            const portraits = [];
                            cards.forEach(card => {
                                const img = card.querySelector('.nikke-numerical-item-left img[src*="sg-tools-cdn"]');
                                portraits.push(img ? img.src : '');
                            });
                            const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
                            const store = pinia?._s?.get('shiftys_nikke_list');
                            const list = store?.$state?.shown_nikke_list || [];
                            const codes = list.map(item => item.name_code);
                            return {portraits, codes};
                        }""")
                        if result:
                            portraits = result.get("portraits", [])
                            codes = result.get("codes", [])
                            for i in range(min(len(portraits), len(codes))):
                                code = codes[i]
                                url = portraits[i]
                                if isinstance(code, int) and url:
                                    mappings[code] = url
                            break

                    logger.info(f"NIKKE 头像映射抓取完成：{len(mappings)} 个角色。")
                    return mappings
                finally:
                    await browser.close()
        except Exception as exc:
            logger.warning(f"NIKKE Playwright 头像抓取失败：{exc}")
            return {}

    async def _download_mappings(self, mappings: dict[int, str]) -> int:
        """下载角色头像图片到本地 portraits/ 目录。"""
        new_count = 0
        for name_code, url in mappings.items():
            path = self.portrait_path(name_code)
            try:
                resp = await self._client.get(url)
                resp.raise_for_status()
                path.write_bytes(resp.content)
                new_count += 1
            except Exception as exc:
                logger.warning(
                    f"NIKKE 头像下载失败 {name_code} ({url}): {exc}", exc_info=True
                )
        if new_count:
            logger.info(f"NIKKE 头像下载完成：{new_count} 个。")
        return new_count
