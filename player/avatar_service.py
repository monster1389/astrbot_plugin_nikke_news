import time
from pathlib import Path

import httpx
from astrbot.api import logger

from player.avatar_mapping_cache import AvatarMappingCache
from player.player_mapping_refresher import parse_cookie_header

SHIFTYSPAD_COMBAT_URL = "https://www.blablalink.com/shiftyspad/nikke-list?type=combat"


class AvatarService:
    """角色头像管理：从 Blablalink CDN 抓取并缓存头像图片。"""

    def __init__(self, data_dir: Path, client: httpx.AsyncClient):
        self._client = client
        self._mapping_cache = AvatarMappingCache(data_dir / "avatar_mappings.json")
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
        mappings = await self._scrape_avatar_mappings(cookie)
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
        mappings = await self._scrape_avatar_mappings(cookie)
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
            mappings = await self._scrape_avatar_mappings(cookie)
        url = mappings.get(name_code)
        if not url:
            return False

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

    async def _scrape_avatar_mappings(self, cookie: str) -> dict[int, str]:
        """用 Playwright 两阶段抓取 name_code→CDN 头像 URL 映射。

        阶段 1：初始渲染窗口（~5s）轮询抓取全部 190 角色默认头像 URL。
        阶段 2：拦截 GetUserCharacters API，注入 Vue store 展开全部已拥有角色，
        大视口 + 滚动采集皮肤 URL 覆盖阶段 1 中已拥有角色的默认 URL。
        """
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

                    # 拦截 CDN JSON 和 GetUserCharacters API（必须在 goto 前注册）
                    cdn_chars = None
                    api_chars = None

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

                    # ── 阶段 1：默认头像 URL（190 角色初始渲染窗口 ~5s）──
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

                    if not mappings:
                        logger.warning(
                            "NIKKE 头像映射轮询超时：10 秒内未检测到 50+ 角色卡片，"
                            "可能页面加载延迟或 DOM 结构变化。"
                        )
                    else:
                        logger.info(f"NIKKE 阶段 1：{len(mappings)} 个默认头像 URL。")

                    # ── 阶段 2：已拥有角色皮肤 URL ──
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

    async def _scrape_obtained_avatars(
        self,
        page,
        default_mappings: dict[int, str],
        cdn_chars: list | None,
        api_chars: dict | None,
    ) -> dict[int, str]:
        """阶段 2：注入全部已拥有角色到 Vue store → 滚动采集皮肤 URL。

        返回 name_code → URL 中与阶段 1 默认 URL 不同的映射。
        """
        if not cdn_chars or not api_chars:
            logger.info("NIKKE 阶段 2：未捕获 CDN/API 数据，跳过皮肤采集。")
            return {}

        api_list = api_chars.get("data", {}).get("characters", [])
        if not api_list:
            logger.info("NIKKE 阶段 2：API 无角色数据，跳过。")
            return {}

        # name_code → CDN entry（O(1) resource_id 查找）
        nc_to_cdn: dict[int, dict] = {
            c["name_code"]: c for c in cdn_chars if "name_code" in c
        }

        # 构造完整 shown_nikke_list（含全部已拥有角色）
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

        # 注入 store
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

        # 大视口展开虚拟列表
        await page.set_viewport_size({"width": 1280, "height": 30000})
        await page.wait_for_timeout(3000)

        # 滚动 #layout-content 逐段采集皮肤 URL
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

        # 仅返回与阶段 1 默认 URL 不同的（即皮肤 URL）
        obtained_mappings = {
            code: url
            for code, url in all_mappings.items()
            if url != default_mappings.get(code, "")
        }

        if obtained_mappings:
            logger.info(
                f"NIKKE 阶段 2：{len(obtained_mappings)} 个皮肤 URL 将覆盖默认。"
            )

        return obtained_mappings

    async def _download_mappings(self, mappings: dict[int, str]) -> int:
        """下载角色头像图片到本地 avatars/ 目录。"""
        if self._avatars_dir:
            self._avatars_dir.mkdir(parents=True, exist_ok=True)
        new_count = 0
        for name_code, url in mappings.items():
            path = self.avatar_path(name_code)
            if path is None:
                continue
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
