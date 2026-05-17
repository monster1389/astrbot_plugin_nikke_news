"""Phase 2 新方案：劫持 GetUserCharacters → 注入 Vue store → 滚动采集全量皮肤 URL。

1. 等待商店初始化后，获取 GetUserCharacters API 返回的 133 个角色
2. 将 shown_nikke_list 替换为全部已获得角色
3. 滚动 #layout-content 采集皮肤 URL
"""

import asyncio
import json

COOKIE_STR = "game_token=5204fa492bf4692f389db02093475f3001ec998f; game_openid=16019721895011516558; game_channelid=131; game_gameid=29080"
URL = "https://www.blablalink.com/shiftyspad/nikke-list?type=combat"


def make_cookies(s):
    cookies = []
    for part in s.split(";"):
        if "=" not in part:
            continue
        n, v = part.split("=", 1)
        n, v = n.strip(), v.strip()
        if not n:
            continue
        for d in (".blablalink.com", "www.blablalink.com"):
            cookies.append(
                {
                    "name": n,
                    "value": v,
                    "domain": d,
                    "path": "/",
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "Lax",
                }
            )
    return cookies


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="zh-TW", viewport={"width": 1280, "height": 900}
        )
        await ctx.add_cookies(make_cookies(COOKIE_STR))
        page = await ctx.new_page()

        # 拦截 CDN JSON 和 GetUserCharacters
        cdn_chars = None
        api_chars = None

        async def on_response(response):
            nonlocal cdn_chars, api_chars
            url = response.url
            if "sg-tools-cdn" in url and url.endswith(".json") and not cdn_chars:
                try:
                    data = await response.json()
                    if isinstance(data, list) and data and "name_code" in data[0]:
                        cdn_chars = data
                except Exception:
                    pass
            if "GetUserCharacters" in url and not api_chars:
                try:
                    api_chars = await response.json()
                except Exception:
                    pass

        page.on("response", on_response)
        await page.goto(URL, wait_until="load", timeout=60000)

        # 等待 API 和 CDN 数据加载
        for _ in range(30):
            if cdn_chars and api_chars:
                break
            await page.wait_for_timeout(500)
        else:
            print("超时等待 API/CDN 数据")
            await ctx.close()
            await browser.close()
            return

        chars = api_chars.get("data", {}).get("characters", [])
        print(f"API: {len(chars)} obtained chars")
        print(f"CDN: {len(cdn_chars)} total chars")

        # 构建: resource_id → CDN entry (含 costumes)
        rid_to_cdn = {}
        for c in cdn_chars:
            rid_to_cdn[c.get("resource_id")] = c

        # 构建: name_code → API char data

        # 构建新的 shown_nikke_list: 包含全部 133 obtained 角色
        new_list = []
        for c in chars:
            nc = c["name_code"]
            # 从 CDN 找到对应的 resource_id
            rid = None
            cdn_entry = None
            for cdn in cdn_chars:
                if cdn["name_code"] == nc:
                    rid = cdn["resource_id"]
                    cdn_entry = cdn
                    break

            # 确定 used_costume_index
            costume_id = c.get("costume_id", 0)
            used_ci = 0  # default
            if costume_id != 0 and cdn_entry:
                for cos in cdn_entry.get("costumes", []):
                    if cos["id"] == costume_id:
                        used_ci = cos["costume_index"]
                        break

            new_list.append(
                {
                    "name_code": nc,
                    "resource_id": rid or 0,
                    "is_obtained": True,
                    "costume_id": costume_id,
                    "used_costume_index": used_ci,
                    # minimal fields to satisfy Vue component
                    "grade": c.get("grade", 0),
                    "lv": c.get("lv", 0),
                    "combat": c.get("combat", 0),
                    "core": c.get("core", 0),
                }
            )

        print(f"构建新 shown_nikke_list: {len(new_list)} 条")

        # 注入 store
        inject_result = await page.evaluate(
            """(newList) => {
            const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
            if (!pinia) return 'no pinia';
            const s = pinia._s.get('shiftys_nikke_list');
            if (!s || !s.$state) return 'no store';
            s.$state.shown_nikke_list = newList;
            s.$state.is_all_loaded = true;
            s.$state.is_loading = false;
            return 'injected: ' + newList.length;
        }""",
            new_list,
        )
        print(f"注入结果: {inject_result}")

        # 等 Vue 反应
        await page.wait_for_timeout(3000)

        # 检查 store 状态
        store_check = await page.evaluate("""() => {
            const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
            const s = pinia?._s?.get('shiftys_nikke_list');
            if (!s || !s.$state) return null;
            return {
                shown: s.$state.shown_nikke_list.length,
                first5: s.$state.shown_nikke_list.slice(0, 5).map(i => ({nc: i.name_code, cid: i.costume_id})),
            };
        }""")
        print(f"Store after inject: {json.dumps(store_check)}")

        # 大视口展开
        await page.set_viewport_size({"width": 1280, "height": 30000})
        await page.wait_for_timeout(3000)

        # 检查 DOM 卡片数量
        dom_check = await page.evaluate("""() => {
            const cards = document.querySelectorAll('[data-cname="card-item"]');
            const imgs = document.querySelectorAll('[data-cname="card-item"] img[src*="sg-tools-cdn"]');
            return {cards: cards.length, imgs: imgs.length};
        }""")
        print(f"DOM after inject+bigViewport: {dom_check}")

        # 滚动 #layout-content 采集
        all_mappings = {}
        prev_sh = -1
        prev_accum = 0
        stall = 0

        for step in range(50):
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
                before = len(all_mappings)
                for k, v in result["mappings"].items():
                    all_mappings[int(k)] = v
                new_cards = len(all_mappings) - before
            else:
                new_cards = 0

            info = await page.evaluate("""() => {
                const el = document.querySelector('#layout-content');
                if (!el) return null;
                return {
                    scrollTop: el.scrollTop, scrollHeight: el.scrollHeight,
                    clientHeight: el.clientHeight,
                    imgCount: document.querySelectorAll('[data-cname="card-item"] img[src*="sg-tools-cdn"]').length,
                };
            }""")
            if not info:
                break

            sh = info["scrollHeight"]
            print(
                f"  step {step:2d}: top={info['scrollTop']:5d} sh={sh:5d} "
                f"imgs={info['imgCount']:3d} accum={len(all_mappings):3d} (+{new_cards})"
            )

            if sh == prev_sh and len(all_mappings) == prev_accum:
                stall += 1
                if stall >= 3:
                    break
            else:
                stall = 0
            prev_sh = sh
            prev_accum = len(all_mappings)

            if len(all_mappings) >= len(chars):
                break

            await page.evaluate("""() => {
                const el = document.querySelector('#layout-content');
                if (el) { el.scrollTop += el.clientHeight; el.dispatchEvent(new Event('scroll', {bubbles: true})); }
            }""")
            await page.wait_for_timeout(600)

        print(f"\n=== 采集结果: {len(all_mappings)} / {len(chars)} ===")

        # 找皮肤 URL（与默认不同的）
        try:
            with open(
                "/home/lxx/DockerData/astrbot/data/plugin_data/astrbot_plugin_nikke_news/avatar_mappings.json"
            ) as f:
                cache = json.load(f).get("mappings", {})
        except Exception:
            cache = {}

        diffs = []
        for code, url in sorted(all_mappings.items()):
            old = cache.get(str(code), "")
            if old and old != url:
                diffs.append((code, old, url))
        if diffs:
            print(f"皮肤 URL ({len(diffs)}):")
            for code, old, new in diffs:
                print(f"  nc={code}: {new[-80:]}")
        else:
            print("没有皮肤差异")

        await ctx.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
