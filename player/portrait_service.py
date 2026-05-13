from pathlib import Path

import httpx
from astrbot.api import logger

from player.player_mapping_refresher import _parse_cookie_header

SHIFTYSPAD_COMBAT_URL = "https://www.blablalink.com/shiftyspad/nikke-list?type=combat"


class PortraitService:
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
                "2. 当前环境是否安装了 Playwright\n"
                "3. 账号是否拥有角色（？type=combat 需要账号有角色才能抓到头像）"
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

    # ------------------------------------------------------------------
    # private
    # ------------------------------------------------------------------

    async def _scrape_portrait_mappings(self, cookie: str) -> dict[int, str]:
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
                    cookies = _parse_cookie_header(cookie)
                    if cookies:
                        await context.add_cookies(cookies)
                    page = await context.new_page()

                    await page.goto(
                        SHIFTYSPAD_COMBAT_URL, wait_until="load", timeout=60000
                    )
                    await page.wait_for_timeout(5000)

                    prev_count = 0
                    stall_count = 0

                    for _attempt in range(40):
                        await page.evaluate("""() => {
                            const all = document.querySelectorAll('#app div');
                            let container = null;
                            let maxDiff = 0;
                            for (const el of all) {
                                const diff = el.scrollHeight - el.clientHeight;
                                if (diff > maxDiff && diff > 50) {
                                    maxDiff = diff;
                                    container = el;
                                }
                            }
                            if (container) {
                                container.dispatchEvent(new WheelEvent('wheel', {
                                    deltaY: 500, deltaMode: 0, bubbles: true, cancelable: true,
                                }));
                            }
                        }""")
                        await page.mouse.wheel(0, 500)
                        await page.wait_for_timeout(1500)

                        snap = await page.evaluate("""() => {
                            const cards = document.querySelectorAll('[data-cname="card-item"]');
                            const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
                            const store = pinia?._s?.get('shiftys_nikke_list');
                            return {
                                cardCount: cards.length,
                                isAllLoaded: store?.$state?.is_all_loaded || false,
                            };
                        }""")

                        if snap["cardCount"] != prev_count:
                            prev_count = snap["cardCount"]
                            stall_count = 0
                        else:
                            stall_count += 1

                        if snap["isAllLoaded"]:
                            break
                        if stall_count > 10:
                            break

                    result = await page.evaluate("""() => {
                        const portraits = [];
                        document.querySelectorAll('[data-cname="card-item"]').forEach(card => {
                            const img = card.querySelector('.nikke-numerical-item-left img[src*="sg-tools-cdn"]');
                            portraits.push(img ? img.src : '');
                        });
                        const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
                        const store = pinia?._s?.get('shiftys_nikke_list');
                        const list = store?.$state?.shown_nikke_list || [];
                        const codes = list.map(item => item.name_code);
                        return {portraits, codes};
                    }""")

                    mappings: dict[int, str] = {}
                    portraits = result.get("portraits", [])
                    codes = result.get("codes", [])
                    for i in range(min(len(portraits), len(codes))):
                        code = codes[i]
                        url = portraits[i]
                        if isinstance(code, int) and url:
                            mappings[code] = url

                    logger.info(f"NIKKE 头像映射抓取完成：{len(mappings)} 个角色。")
                    return mappings
                finally:
                    await browser.close()
        except Exception as exc:
            logger.warning(f"NIKKE Playwright 头像抓取失败：{exc}")
            return {}

    async def _download_mappings(self, mappings: dict[int, str]) -> int:
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
