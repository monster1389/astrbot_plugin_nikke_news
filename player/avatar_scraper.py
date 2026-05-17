"""Playwright 头像映射抓取：拦截 CDN JSON → 注入全部角色 → 一次采集 name_code → CDN URL。"""

from player.avatar_mapping_cache import AvatarMappingCache
from player.player_mapping_refresher import parse_cookie_header

from astrbot.api import logger

SHIFTYSPAD_COMBAT_URL = "https://www.blablalink.com/shiftyspad/nikke-list?type=combat"


class AvatarScraper:
    """用 Playwright 一次性抓取 name_code → CDN 头像 URL 映射。

    拦截 CDN 角色 JSON（全部 ~190 角色）和 GetUserCharacters API（已拥有角色），
    构建完整角色列表注入 Vue store，放大视口渲染全部卡片，滚动采集所有头像 URL。
    已拥有角色自动带有皮肤 URL，未拥有角色为默认头像。
    """

    def __init__(self, mapping_cache: AvatarMappingCache):
        self._mapping_cache = mapping_cache

    async def scrape(self, cookie: str) -> dict[int, str]:
        """执行抓取，保存到缓存，返回完整 name_code → URL 映射。"""
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

                    cdn_chars: list | None = None
                    api_chars: dict | None = None

                    async def _on_response(response):
                        nonlocal cdn_chars, api_chars
                        url = response.url
                        if (
                            "sg-tools-cdn" in url
                            and url.endswith(".json")
                            and not cdn_chars
                        ):
                            try:
                                data = await response.json()
                                if (
                                    isinstance(data, list)
                                    and data
                                    and "name_code" in data[0]
                                ):
                                    cdn_chars = data
                            except Exception:
                                pass
                        if "GetUserCharacters" in url and not api_chars:
                            try:
                                api_chars = await response.json()
                            except Exception:
                                pass

                    page.on("response", _on_response)
                    await page.goto(
                        SHIFTYSPAD_COMBAT_URL, wait_until="load", timeout=60000
                    )

                    # Wait for CDN and API responses
                    for _ in range(30):
                        if cdn_chars and api_chars:
                            break
                        await page.wait_for_timeout(200)

                    if not cdn_chars:
                        logger.warning(
                            "NIKKE 头像映射抓取失败：6 秒内未捕获 CDN 角色数据，"
                            "可能页面加载延迟或网络问题。"
                        )
                        return {}

                    if not api_chars:
                        logger.info(
                            "NIKKE 未捕获 GetUserCharacters 响应，将仅采集默认头像。"
                        )

                    mappings = await self._scrape_all_avatars(
                        page, cdn_chars, api_chars
                    )

                    logger.info(f"NIKKE 头像映射抓取完成：{len(mappings)} 个角色。")
                    if mappings:
                        self._mapping_cache.save(mappings)
                    return mappings
                finally:
                    await browser.close()
        except Exception as exc:
            logger.warning(f"NIKKE Playwright 头像抓取失败：{exc}")
            return {}

    async def _scrape_all_avatars(
        self,
        page,
        cdn_chars: list,
        api_chars: dict | None,
    ) -> dict[int, str]:
        """注入全部 CDN 角色到 Vue store，渲染后滚动采集所有头像 URL。

        已拥有角色使用 API 提供的 costume_id 以获取皮肤 URL；
        未拥有角色使用 costume_id=0 获取默认头像。
        """
        api_list = api_chars.get("data", {}).get("characters", []) if api_chars else []
        obtained_by_code: dict[int, dict] = {}
        for c in api_list:
            nc = c.get("name_code")
            if isinstance(nc, int):
                obtained_by_code[nc] = c

        # Build injection list from all CDN characters
        new_list: list[dict] = []
        for c in cdn_chars:
            nc = c.get("name_code")
            if not isinstance(nc, int):
                continue
            obtained = obtained_by_code.get(nc)
            new_list.append(
                {
                    "name_code": nc,
                    "resource_id": c.get("resource_id", 0),
                    "is_obtained": True,
                    "costume_id": (obtained.get("costume_id", 0) if obtained else 0),
                    "grade": obtained.get("grade", 0) if obtained else 0,
                    "lv": obtained.get("lv", 0) if obtained else 0,
                    "combat": obtained.get("combat", 0) if obtained else 0,
                    "core": obtained.get("core", 0) if obtained else 0,
                }
            )

        injected = await page.evaluate(
            """(newList) => {
            const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
            if (!pinia) return false;
            const s = pinia._s.get('shiftys_nikke_list');
            if (!s || !s.$state) return false;
            s.$state.shown_nikke_list = newList;
            s.$state.is_all_loaded = true;
            s.$state.is_loading = false;
            return true;
        }""",
            new_list,
        )

        if not injected:
            logger.warning(
                "NIKKE 头像抓取失败：注入 Vue store 失败（Vue/Pinia 结构可能已变化）。"
            )
            return {}

        logger.info(
            f"NIKKE 已注入 {len(new_list)} 个角色（"
            f"{len(obtained_by_code)} 个已拥有），开始渲染采集..."
        )

        # Render all cards with a viewport tall enough to avoid virtual culling
        await page.set_viewport_size({"width": 1280, "height": 30000})
        await page.wait_for_timeout(3000)

        all_mappings: dict[int, str] = {}
        prev_sh = -1
        prev_accum = 0
        stall = 0

        for _ in range(50):
            result = await page.evaluate("""() => {
                const cards = document.querySelectorAll('[data-cname="card-item"]');
                const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
                const store = pinia?._s?.get('shiftys_nikke_list');
                const list = store?.$state?.shown_nikke_list || [];
                const mappings = {};
                for (let i = 0; i < Math.min(cards.length, list.length); i++) {
                    const img = cards[i].querySelector('.nikke-numerical-item-left img[src*="sg-tools-cdn"]');
                    const code = list[i]?.name_code;
                    const url = img ? img.src : '';
                    if (typeof code === 'number' && url) mappings[code] = url;
                }
                return {mappings, cardCount: cards.length};
            }""")

            if result and result.get("mappings"):
                for k, v in result["mappings"].items():
                    all_mappings[int(k)] = v

            info = await page.evaluate("""() => {
                const el = document.querySelector('#layout-content');
                if (!el) return null;
                return {
                    scrollTop: el.scrollTop, scrollHeight: el.scrollHeight,
                    clientHeight: el.clientHeight,
                };
            }""")
            if not info:
                break

            sh = info["scrollHeight"]
            if sh == prev_sh and len(all_mappings) == prev_accum:
                stall += 1
                if stall >= 3:
                    break
            else:
                stall = 0
            prev_sh = sh
            prev_accum = len(all_mappings)

            if len(all_mappings) >= len(new_list):
                break

            await page.evaluate("""() => {
                const el = document.querySelector('#layout-content');
                if (el) {
                    el.scrollTop += el.clientHeight;
                    el.dispatchEvent(new Event('scroll', {bubbles: true}));
                }
            }""")
            await page.wait_for_timeout(600)

        logger.info(f"NIKKE 采集完成：{len(all_mappings)}/{len(new_list)} 个角色 URL。")

        return all_mappings
