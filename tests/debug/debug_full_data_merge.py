"""找 Vue 内部的 CDN JSON 数据和用户 costume 数据，合成全量 portrait URL。"""

import asyncio

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

        # 拦截关键 API 响应
        cdn_chars = None
        api_chars = None

        async def on_response(response):
            nonlocal cdn_chars, api_chars
            url = response.url
            if "sg-tools-cdn" in url and url.endswith(".json") and not cdn_chars:
                try:
                    data = await response.json()
                    if (
                        isinstance(data, list)
                        and data
                        and "name_code" in data[0]
                        and "resource_id" in data[0]
                    ):
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
        await page.wait_for_timeout(15000)

        if cdn_chars:
            print(f"CDN JSON: {len(cdn_chars)} characters")
            # Build resource_id -> name_code map
            rid_to_nc = {}
            nc_to_data = {}
            for c in cdn_chars:
                nc = c.get("name_code")
                rid = c.get("resource_id")
                if nc and rid:
                    rid_to_nc[rid] = nc
                    nc_to_data[nc] = {
                        "resource_id": rid,
                        "costumes": c.get("costumes", []),
                    }

        if api_chars:
            api_list = api_chars.get("data", {}).get("characters", [])
            print(f"API GetUserCharacters: {len(api_list)} characters")
            # Build name_code -> costume_id
            nc_to_costume = {}
            for c in api_list:
                nc = c.get("name_code")
                cid = c.get("costume_id", 0)
                if nc:
                    nc_to_costume[nc] = cid

        if cdn_chars and api_chars:
            # Merge: for each CDN character, determine portrait URL
            nc_to_costume = {}
            for c in api_chars.get("data", {}).get("characters", []):
                nc = c.get("name_code")
                cid = c.get("costume_id", 0)
                if nc:
                    nc_to_costume[nc] = cid

            # Build costume_index lookup from CDN data
            # CDN costumes: [{id: 30064, costume_index: 2}, {id: 120004, costume_index: 1}]
            costume_id_to_index = {}
            for nc, data in nc_to_data.items():
                for costume in data["costumes"]:
                    costume_id_to_index[costume["id"]] = costume["costume_index"]

            # For each obtained character, find which costume_index is equipped
            print("\n=== 已拥有角色 skin 分析 ===")
            non_zero = 0
            for nc, cid in sorted(nc_to_costume.items()):
                if cid != 0:
                    non_zero += 1
                    cinfo = nc_to_data.get(nc, {})
                    rid = cinfo.get("resource_id", "?")
                    ci = costume_id_to_index.get(cid, "?")
                    print(
                        f"  name_code={nc} resource_id={rid} costume_id={cid} → costume_index={ci}"
                    )

            print(f"\n非零 costume_id: {non_zero} / {len(nc_to_costume)} obtained")
            print(f"CDN 全部角色: {len(nc_to_data)}")
            print(f"未拥有: {len(nc_to_data) - len(nc_to_costume)}")

            # Now we need: for each (resource_id, costume_index) → CDN webp URL
            # We have Phase 1 URLs for default (costume_index=1)
            # We need the skinned URLs for non-default costume_index

            # Try: use DOM's current state to capture any rendered portraits
            dom_mappings = await page.evaluate("""() => {
                const cards = document.querySelectorAll('[data-cname="card-item"]');
                const mappings = {};
                cards.forEach(card => {
                    const img = card.querySelector('.nikke-numerical-item-left img[src*="sg-tools-cdn"]');
                    if (img) {
                        // Get name_code from the card somehow
                        // Or just collect all unique CDN URLs
                        mappings[img.src] = true;
                    }
                });
                return Object.keys(mappings);
            }""")
            print(f"\nDOM 中当前 CDN URLs: {len(dom_mappings)} unique")
            for u in dom_mappings[:5]:
                print(f"  {u[-80:]}")

        await ctx.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
