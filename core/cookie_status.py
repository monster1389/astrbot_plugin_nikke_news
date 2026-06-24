# core/cookie_status.py
"""Cookie 可用性状态枚举。"""

from enum import Enum, auto


class CookieStatus(Enum):
    """Cookie 可用状态。"""

    AVAILABLE = auto()
    DISABLED = auto()
    EMPTY = auto()
    INVALID = auto()
