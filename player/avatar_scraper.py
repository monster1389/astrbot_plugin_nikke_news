"""Playwright 头像映射抓取：两阶段采集 name_code → CDN URL。"""

from player.avatar_mapping_cache import AvatarMappingCache
from player.player_mapping_refresher import parse_cookie_header

from astrbot.api import logger

SHIFTYSPAD_COMBAT_URL = "https://www.blablalink.com/shiftyspad/nikke-list?type=combat"


class AvatarScraper:
    """用 Playwright 两阶段抓取 name_code → CDN 头像 URL 映射。

    阶段 1：页面自然渲染后轮询 DOM 采集全部 ~190 角色默认头像 URL。
    阶段 2：拦截 GetUserCharacters API，注入 Vue store 展开已拥有角色，
    放大视口滚动采集皮肤 URL，覆盖阶段 1 中已拥有角色的默认 URL。
    """

    def __init__(self, mapping_cache: AvatarMappingCache):
        self._mapping_cache = mapping_cache

    async def scrape(self, cookie: str) -> dict[int, str]:
        """执行两阶段抓取，保存到缓存，返回完整 name_code → URL 映射。"""
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

                    mappings = await self._scrape_default_avatars(page)

                    if not mappings:
                        logger.warning(
                            "NIKKE 头像映射轮询超时：10 秒内未检测到 50+ 角色卡片，"
                            "可能页面加载延迟或 DOM 结构变化。"
                        )
                    else:
                        logger.info(f"NIKKE 阶段 1：{len(mappings)} 个默认头像 URL。")

                    obtained_mappings = await self._scrape_obtained_avatars(
                        page, mappings, cdn_chars, api_chars
                    )
                    if obtained_mappings:
                        mappings.update(obtained_mappings)

                    logger.info(
                        f"NIKKE 头像映射抓取完成：{len(mappings)} 个角色"
                        + (
                            f"（{len(obtained_mappings)} 个皮肤 URL）"
                            if obtained_mappings
                            else ""
                        )
                    )
                    if mappings:
                        self._mapping_cache.save(mappings)
                    return mappings
                finally:
                    await browser.close()
        except Exception as exc:
            logger.warning(f"NIKKE Playwright 头像抓取失败：{exc}")
            return {}

    async def _scrape_default_avatars(self, page) -> dict[int, str]:
        """阶段 1：轮询 DOM 从页面自然渲染的卡片中采集默认头像 URL。"""
        mappings: dict[int, str] = {}
        had_window = False

        for _ in range(50):
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
            if result and result.get("codes"):
                had_window = True
                portraits = result.get("portraits", [])
                codes = result.get("codes", [])
                for i in range(min(len(portraits), len(codes))):
                    code = codes[i]
                    url = portraits[i]
                    if isinstance(code, int) and url:
                        mappings[code] = url
            elif had_window:
                break
            await page.wait_for_timeout(200)

        return mappings

    async def _scrape_obtained_avatars(
        self,
        page,
        default_mappings: dict[int, str],
        cdn_chars: list | None,
        api_chars: dict | None,
    ) -> dict[int, str]:
        """阶段 2：注入已拥有角色到 Vue store → 滚动采集皮肤 URL。

        只返回与阶段 1 默认 URL 不同的皮肤 URL。
        """
        if not cdn_chars or not api_chars:
            logger.info("NIKKE 阶段 2：未捕获 CDN/API 数据，跳过皮肤采集。")
            return {}

        api_list = api_chars.get("data", {}).get("characters", [])
        if not api_list:
            logger.info("NIKKE 阶段 2：API 无角色数据，跳过。")
            return {}

        nc_to_cdn: dict[int, dict] = {
            c["name_code"]: c for c in cdn_chars if "name_code" in c
        }

        new_list = []
        for c in api_list:
            nc = c["name_code"]
            cdn_entry = nc_to_cdn.get(nc, {})
            new_list.append(
                {
                    "name_code": nc,
                    "resource_id": cdn_entry.get("resource_id", 0),
                    "is_obtained": True,
                    "costume_id": c.get("costume_id", 0),
                    "grade": c.get("grade", 0),
                    "lv": c.get("lv", 0),
                    "combat": c.get("combat", 0),
                    "core": c.get("core", 0),
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
                "NIKKE 阶段 2：注入 store 失败（Vue/Pinia 结构可能已变化）。"
            )
            return {}

        logger.info(
            f"NIKKE 阶段 2：已注入 {len(new_list)} 个已拥有角色，开始滚动采集..."
        )

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

        logger.info(
            f"NIKKE 阶段 2：采集 {len(all_mappings)}/{len(new_list)} 个已拥有角色 URL。"
        )

        return {
            code: url
            for code, url in all_mappings.items()
            if url != default_mappings.get(code, "")
        }
