"""时间工具：按北京时区 4 点分界计算 day_key、Cookie 过期检测。"""

from datetime import datetime, timedelta


def day_key(now: datetime) -> str:
    pivot = now
    if now.hour < 4:
        pivot = now - timedelta(days=1)
    return pivot.strftime("%Y-%m-%d")


def is_cookie_invalid_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "player_api_error" in text or "401" in text or "cookie" in text
