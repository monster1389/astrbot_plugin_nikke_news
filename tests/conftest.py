import logging
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_module(name: str, **attrs: object) -> ModuleType:
    mod = ModuleType(name)
    mod.__dict__.update(attrs)
    return mod


_mock_api = _make_module("astrbot.api")
_mock_api_event = _make_module("astrbot.api.event")
_mock_api_star = _make_module("astrbot.api.star")

# ---------------------------------------------------------------------------
# logger – a real Python logger captured by caplog
# ---------------------------------------------------------------------------
_logger = logging.getLogger("astrbot_plugin_nikke_news")
_logger.setLevel(logging.DEBUG)

# ---------------------------------------------------------------------------
# AstrBotConfig – dict alias
# ---------------------------------------------------------------------------
AstrBotConfig = dict

# ---------------------------------------------------------------------------
# MessageChain
# ---------------------------------------------------------------------------
class MessageChain:
    def __init__(self):
        self._content = ""

    def message(self, text: str) -> "MessageChain":
        self._content = text
        return self

    def __repr__(self):
        return f"MessageChain({self._content!r})"


# ---------------------------------------------------------------------------
# Star base class
# ---------------------------------------------------------------------------
class Context:
    pass


class Star:
    def __init__(self, context: Context, config: dict | None = None):
        pass


# ---------------------------------------------------------------------------
# StarTools – records calls for assertions
# ---------------------------------------------------------------------------
_SENT_MESSAGES: list[dict] = []


def _reset_sent() -> None:
    _SENT_MESSAGES.clear()


class StarTools:
    @staticmethod
    def get_data_dir(name: str) -> Path:
        import tempfile

        return Path(tempfile.mkdtemp(prefix=f"test_{name}_"))

    @staticmethod
    async def send_message_by_id(
        target_type: str,
        target_id: str,
        message_chain: MessageChain,
        platform: str = "aiocqhttp",
    ) -> None:
        _SENT_MESSAGES.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "content": message_chain._content,
                "platform": platform,
            }
        )


# ---------------------------------------------------------------------------
# register decorator – no-op passthrough
# ---------------------------------------------------------------------------
def register(name: str, author: str, desc: str, version: str):
    def deco(cls):
        cls._plugin_meta = {
            "name": name,
            "author": author,
            "desc": desc,
            "version": version,
        }
        return cls

    return deco


# ---------------------------------------------------------------------------
# Wire up sys.modules
# ---------------------------------------------------------------------------
_mock_api.__dict__.update(
    AstrBotConfig=AstrBotConfig,
    logger=_logger,
)
_mock_api_event.__dict__.update(MessageChain=MessageChain)
_mock_api_star.__dict__.update(
    Context=Context,
    Star=Star,
    StarTools=StarTools,
    register=register,
)

sys.modules["astrbot"] = _make_module("astrbot")
sys.modules["astrbot.api"] = _mock_api
sys.modules["astrbot.api.event"] = _mock_api_event
sys.modules["astrbot.api.star"] = _mock_api_star


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def reset_sent():
    _reset_sent()
    yield
    _reset_sent()


@pytest.fixture
def captured():
    return _SENT_MESSAGES


@pytest.fixture
def logger():
    return _logger
