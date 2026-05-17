"""抓 GetUserCharacters 完整 133 角色数据，看有没有 costume_id / portrait 字段。"""

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

        chars_body = None

        async def on_response(response):
            nonlocal chars_body
            if "GetUserCharacters" in response.url:
                try:
                    chars_body = await response.json()
                except Exception:
                    pass

        page.on("response", on_response)
        await page.goto(URL, wait_until="load", timeout=60000)
        await page.wait_for_timeout(15000)

        if not chars_body:
            print("未捕获到 GetUserCharacters 响应")
            await ctx.close()
            await browser.close()
            return

        chars = chars_body.get("data", {}).get("characters", [])
        print(f"GetUserCharacters: {len(chars)} characters\n")

        # 分析每个角色的字段
        all_keys = set()
        for c in chars:
            for k in c.keys():
                all_keys.add(k)
        print(f"所有字段 ({len(all_keys)}): {sorted(all_keys)}")

        # 展示第一个角色
        print("\n第一个角色:")
        print(json.dumps(chars[0], ensure_ascii=False, indent=2)[:1500])

        # 统计有关 costume/skin/icon/image 的字段
        print("\n=== 逐角色 costume 数据 ===")
        for c in chars[:20]:
            nc = c.get("name_code", "?")
            costume_id = c.get("costume_id", "?")
            costume_tid = c.get("costume_tid", "?")
            resource_id = c.get("resource_id", "?")
            grade = c.get("grade", "?")
            lv = c.get("lv", "?")
            print(
                f"  name_code={nc} resource_id={resource_id} costume_id={costume_id} costume_tid={costume_tid} lv={lv} grade={grade}"
            )

        # 统计 costume_id 分布
        from collections import Counter

        costume_counts = Counter()
        for c in chars:
            cid = c.get("costume_id", 0)
            costume_counts[cid] += 1
        print(f"\ncostume_id 分布: {costume_counts.most_common(20)}")

        # 检查 costume_tid 分布
        tid_counts = Counter()
        for c in chars:
            tid = c.get("costume_tid", 0)
            tid_counts[tid] += 1
        print(f"costume_tid 分布 (top 20): {tid_counts.most_common(20)}")

        # name_code 列表
        name_codes = [c.get("name_code") for c in chars]
        print(f"\nname_codes ({len(name_codes)}): {sorted(name_codes)[:30]}...")
        print("与 shown_nikke_list 中的比较:")
        snl_codes = [5170, 5129, 5169, 5124, 5161, 5156, 5105, 5066, 5101, 1021]
        api_codes_set = set(name_codes)
        snl_set = set(snl_codes)
        print(f"  API 有而 store 无: {len(api_codes_set - snl_set)}")
        print(f"  Store 有而 API 无: {len(snl_set - api_codes_set)}")

        await ctx.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
