"""通过 Playwright 从 Blablalink CDN 抓取角色名和词条映射。"""

import asyncio
from typing import Any

from astrbot.api import logger

from core.browser_context import browser_context, BrowserLaunchError
from core.constants import CDN_HOST
from core.utils import accept_language

SHIFTYSPAD_NIKKE_LIST_URL = (
    "https://www.blablalink.com/shiftyspad/nikke-list?type=combat"
)


class PlayerMappingRefreshError(Exception):
    """角色映射刷新失败异常。"""


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
    """从 equip_table JSON 提取 T10 词条 option 映射。"""
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


def extract_resource_ids(data: Any) -> dict[int, int]:
    """从 CDN 角色列表 JSON 提取 name_code → resource_id 映射。

    Args:
        data: CDN JSON 数据（预期为 list[dict]）。

    Returns:
        {name_code: resource_id} 映射字典。
    """
    if not isinstance(data, list):
        return {}
    result: dict[int, int] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        code = item.get("name_code")
        rid = item.get("resource_id")
        if isinstance(code, int) and isinstance(rid, int):
            result[code] = rid
    return result


async def refresh_player_mappings(
    *,
    cookie_header: str,
    language: str = "en",
    timeout_ms: int = 20000,
) -> tuple[
    dict[int, str],
    dict[str, dict[str, Any]],
    dict[str, dict[str, str]],
    dict[int, int],
]:
    """启动 Chromium 访问 Blablalink 尼姬列表页，拦截 CDN 响应抓取角色名和词条。

    Args:
        cookie_header: Cookie 请求头字符串。
        language: 目标语言代码，默认 en。
        timeout_ms: 页面加载超时毫秒数，默认 20000。

    Returns:
        (角色名映射, 词条选项映射, CDN 来源元数据, resource_id 映射) 元组。
            resource_ids: name_code → CDN resource_id 的映射字典。

    Raises:
        PlayerMappingRefreshError: Playwright 不可用、页面超时或未捕获到数据。
    """
    character_names: dict[int, str] = {}
    resource_ids: dict[int, int] = {}
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
            logger.debug("角色映射 CDN JSON 解析失败", exc_info=True)
            return

        found_names = extract_character_names(data)
        found_options = extract_state_effect_options(data)
        if not found_names and not found_options:
            logger.debug(f"角色映射 CDN 响应未提取到数据：{url}")
            return

        logger.debug(
            f"角色映射 CDN 响应：角色 {len(found_names)} 个，词条 {len(found_options)} 个"
        )
        found_resource_ids = extract_resource_ids(data)
        if found_resource_ids:
            resource_ids.update(found_resource_ids)

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
        async with browser_context(
            cookie_header=cookie_header,
            language=language,
            extra_http_headers={
                "Accept-Language": accept_language(language),
                "x-language": language,
            },
        ) as page:

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
    except BrowserLaunchError as exc:
        raise PlayerMappingRefreshError(str(exc)) from exc
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
    return character_names, options, sources, resource_ids


def _localized_text(value: Any) -> str:
    """从 Blablalink 多语言字段（str 或 {name, description} dict）提取文本。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "description", "en", "zh-TW", "ja", "ko"):
            text = str(value.get(key, "") or "").strip()
            if text:
                return text
    return ""
