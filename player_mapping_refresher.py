import asyncio
from typing import Any

from astrbot.api import logger

SHIFTYSPAD_NIKKE_LIST_URL = "https://www.blablalink.com/shiftyspad/nikke-list?type=combat"
CDN_HOST = "sg-tools-cdn.blablalink.com"


class PlayerMappingRefreshError(Exception):
    pass


def extract_character_names(data: Any) -> dict[int, str]:
    """Extract name_code → character name from pre-localized CDN JSON."""
    if not isinstance(data, list):
        return {}

    result: dict[int, str] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        code = item.get("name_code")
        if not isinstance(code, int):
            continue
        name = _localized_text(item.get("name_localkey"))
        if name:
            result[code] = name
    return result


def extract_state_effect_options(data: Any) -> dict[str, dict[str, Any]]:
    rows: list[dict[str, Any]]
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        rows = [item for item in data["records"] if isinstance(item, dict)]
    elif isinstance(data, list):
        rows = [item for item in data if isinstance(item, dict)]
    else:
        return {}

    result: dict[str, dict[str, Any]] = {}
    for item in rows:
        effect_ids = item.get("state_effect_id_list")
        if isinstance(effect_ids, (int, str)):
            effect_ids = [effect_ids]
        if not isinstance(effect_ids, list):
            continue

        description = _localized_text(item.get("description_localkey"))
        group_id = item.get("state_effect_group_id", item.get("group_id", 0))
        function_type = item.get("function_type", "")
        metadata = {
            "description": description,
            "group_id": group_id,
            "function_type": function_type,
        }
        for effect_id in effect_ids:
            key = str(effect_id or "").strip()
            if key and key != "0":
                result[key] = dict(metadata)
    return result


async def refresh_player_mappings(
    *,
    cookie_header: str,
    language: str = "en",
    timeout_ms: int = 30000,
) -> tuple[dict[int, str], dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise PlayerMappingRefreshError(
            "当前环境未安装 Playwright，无法刷新玩家映射。"
        ) from exc

    character_names: dict[int, str] = {}
    options: dict[str, dict[str, Any]] = {}
    sources: dict[str, dict[str, str]] = {}
    tasks: set[asyncio.Task] = set()

    async def handle_response(response):
        url = response.url
        if CDN_HOST not in url or not url.endswith(".json"):
            return
        try:
            data = await response.json()
        except Exception:
            return

        found_names = extract_character_names(data)
        found_options = extract_state_effect_options(data)
        if not found_names and not found_options:
            return

        headers = await response.all_headers()
        sources[url] = {
            "etag": headers.get("etag", ""),
            "last_modified": headers.get("last-modified", ""),
        }
        if found_names:
            character_names.update(found_names)
        if found_options:
            options.update(found_options)

    logger.info(f"NIKKE Chromium 刷新玩家映射启动（语言：{language}）...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    extra_http_headers={
                        "Accept-Language": _accept_language(language),
                        "x-language": language,
                    }
                )
                cookies = _parse_cookie_header(cookie_header)
                if cookies:
                    await context.add_cookies(cookies)
                page = await context.new_page()

                def on_response(response):
                    task = asyncio.create_task(handle_response(response))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)

                page.on("response", on_response)
                await page.goto(
                    SHIFTYSPAD_NIKKE_LIST_URL,
                    wait_until="load",
                    timeout=timeout_ms,
                )
                await page.wait_for_timeout(8000)
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                await browser.close()
    except PlayerMappingRefreshError:
        raise
    except Exception as exc:
        logger.warning(f"NIKKE Playwright 刷新玩家映射失败：{exc}")
        raise PlayerMappingRefreshError(f"Chromium 刷新玩家映射失败：{exc}") from exc

    if not character_names and not options:
        raise PlayerMappingRefreshError(
            "未从页面网络响应中捕获到角色或词条映射，请确认登录态和页面是否可访问。"
        )

    logger.info(
        f"NIKKE 玩家映射刷新完成：角色 {len(character_names)} 个，词条 {len(options)} 个"
    )
    return character_names, options, sources


def _localized_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "description", "en", "zh-TW", "ja", "ko"):
            text = str(value.get(key, "") or "").strip()
            if text:
                return text
    return ""


def _parse_cookie_header(cookie_header: str) -> list[dict[str, Any]]:
    cookies: list[dict[str, Any]] = []
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        for domain in (".blablalink.com", "www.blablalink.com"):
            cookies.append(
                {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": "/",
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "Lax",
                }
            )
    return cookies


def _accept_language(language: str) -> str:
    if language == "en":
        return "en-US,en;q=0.9,zh-CN;q=0.6,zh;q=0.5"
    if language == "zh":
        return "zh-CN,zh;q=0.9,en;q=0.6"
    if language == "zh-TW":
        return "zh-TW,zh;q=0.9,en;q=0.6"
    return f"{language};q=1.0,en;q=0.7"
