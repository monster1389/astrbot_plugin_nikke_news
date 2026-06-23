# core/cookie_status.py
from enum import Enum, auto


class CookieStatus(Enum):
    """Cookie 可用状态。"""

    AVAILABLE = auto()
    DISABLED = auto()
    EMPTY = auto()
    INVALID = auto()
