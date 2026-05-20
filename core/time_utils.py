"""时间工具：按北京时区 4 点分界计算 day_key、Cookie 过期检测。"""

from datetime import datetime, timedelta

import httpx


def day_key(now: datetime) -> str:
    """按北京时区 4 点分界计算日期键（YYYY-MM-DD），用于去重。"""
    pivot = now
    if now.hour < 4:
        pivot = now - timedelta(days=1)
    return pivot.strftime("%Y-%m-%d")


def is_cookie_invalid_error(exc: Exception) -> bool:
    """检测异常是否为 Cookie 失效错误。

    Args:
        exc: 捕获的异常。

    Returns:
        True 表示 Cookie 已失效（HTTP 401/403 或 API error code）。
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (401, 403)
    return "PLAYER_API_ERROR" in str(exc)
