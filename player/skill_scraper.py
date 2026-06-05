"""通过 Playwright 访问角色页面拦截 CDN JSON 提取技能数据。"""

import asyncio
from typing import Any

from astrbot.api import logger

from core.constants import CDN_HOST
from core.utils import accept_language

SHIFTYSPAD_NIKKE_URL = "https://www.blablalink.com/shiftyspad/nikke"


class SkillScrapeError(Exception):
    """技能数据抓取失败异常。"""


class SkillScraper:
    """Playwright 驱动：导航至角色页，拦截 CDN 角色详情 JSON。

    Attributes:
        _timeout_ms: 页面加载超时毫秒数。
    """

    def __init__(self, timeout_ms: int = 20000):
        self._timeout_ms = timeout_ms

    @staticmethod
    def _extract_skill_data(data: Any) -> dict[str, Any] | None:
        """从 CDN JSON 提取技能相关字段。

        Args:
            data: CDN 响应 JSON 数据。

        Returns:
            包含 resource_id、name_code、name_localkey 和三个 skill_detail 的 dict，
            若无 skill1_detail 则返回 None。
        """
        if not isinstance(data, dict):
            return None
        skill1 = data.get("skill1_detail")
        if not isinstance(skill1, dict):
            return None
        return {
            "resource_id": data.get("resource_id"),
            "name_code": data.get("name_code"),
            "name_localkey": data.get("name_localkey"),
            "skill1_detail": skill1,
            "skill2_detail": data.get("skill2_detail", {}),
            "ulti_skill_detail": data.get("ulti_skill_detail", {}),
        }

    async def scrape(self, resource_id: int, language: str) -> dict[str, Any]:
        """导航至角色页并拦截技能 CDN JSON。

        Args:
            resource_id: 角色 resource_id。
            language: 目标语言代码。

        Returns:
            提取的技能数据 dict。

        Raises:
            SkillScrapeError: Playwright 不可用、超时或未捕获到数据。
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise SkillScrapeError(
                "当前环境未安装 Playwright，无法获取技能数据。"
            ) from exc

        skill_data: dict[str, Any] | None = None
        skill_data_event = asyncio.Event()

        async def handle_response(response):
            nonlocal skill_data
            url = response.url
            if CDN_HOST not in url or not url.endswith(".json"):
                return
            try:
                data = await response.json()
            except Exception:
                return
            extracted = self._extract_skill_data(data)
            if extracted is not None:
                skill_data = extracted
                skill_data_event.set()

        page_url = f"{SHIFTYSPAD_NIKKE_URL}?from=list&nikke={resource_id}"
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        locale=language,
                        extra_http_headers={
                            "Accept-Language": accept_language(language),
                            "x-language": language,
                        },
                    )
                    page = await context.new_page()
                    page.on("response", handle_response)
                    await page.goto(
                        page_url,
                        wait_until="networkidle",
                        timeout=self._timeout_ms,
                    )
                    try:
                        await asyncio.wait_for(skill_data_event.wait(), timeout=10)
                    except asyncio.TimeoutError:
                        raise SkillScrapeError(
                            f"获取角色技能数据超时 (resource_id={resource_id})"
                        )
                finally:
                    await browser.close()
        except SkillScrapeError:
            raise
        except Exception as exc:
            logger.warning(f"NIKKE 技能抓取失败 (resource_id={resource_id})：{exc}")
            raise SkillScrapeError(f"获取角色技能数据失败：{exc}") from exc

        if skill_data is None:
            raise SkillScrapeError(
                f"未从页面响应中捕获到角色技能数据 (resource_id={resource_id})"
            )
        return skill_data
