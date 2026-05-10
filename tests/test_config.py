import logging

import pytest

from main import NikkeNewsPlugin


def make_plugin(**config) -> NikkeNewsPlugin:
    news_keys = {
        "language",
        "fetch_limit",
        "content_mode",
        "max_images",
        "show_publish_time",
        "scheduled_push_groups",
        "startup_mode",
        "push_delay_seconds",
        "push_prefix",
    }
    base = {
        "enabled": True,
        "news_push": {
            "language": "zh-TW",
            "fetch_limit": 10,
            "push_delay_seconds": 2,
        },
    }
    for key, value in config.items():
        if key in news_keys:
            base["news_push"][key] = value
        else:
            base[key] = value
    return NikkeNewsPlugin(context=None, config=base)


# ---------------------------------------------------------------------------
# _poll_interval_seconds – defaults to 300, min 60
# ---------------------------------------------------------------------------
def test_poll_interval_default():
    plugin = make_plugin()
    assert plugin._poll_interval_seconds() == 300


def test_poll_interval_clamped_min():
    plugin = make_plugin(poll_interval_seconds=30)
    assert plugin._poll_interval_seconds() == 60


def test_poll_interval_normal():
    plugin = make_plugin(poll_interval_seconds=180)
    assert plugin._poll_interval_seconds() == 180


# ---------------------------------------------------------------------------
# _fetch_limit – defaults to 10, clamped 1-50
# ---------------------------------------------------------------------------
def test_fetch_limit_default():
    plugin = make_plugin()
    assert plugin._plugin_config.fetch_limit() == 10


def test_fetch_limit_clamped_min():
    plugin = make_plugin(fetch_limit=0)
    assert plugin._plugin_config.fetch_limit() == 1


def test_fetch_limit_clamped_max():
    plugin = make_plugin(fetch_limit=100)
    assert plugin._plugin_config.fetch_limit() == 50


# ---------------------------------------------------------------------------
# _language – defaults to zh-TW, validates
# ---------------------------------------------------------------------------
def test_language_default():
    plugin = make_plugin()
    assert plugin._plugin_config.language() == "zh-TW"


def test_language_valid():
    for lang in ["zh-TW", "en", "ja", "ko", "zh"]:
        plugin = make_plugin(language=lang)
        assert plugin._plugin_config.language() == lang


def test_language_invalid(caplog):
    caplog.set_level(logging.WARNING)
    plugin = make_plugin(language="fr")
    assert plugin._plugin_config.language() == "zh-TW"
    assert "语言配置无效" in caplog.text


def test_language_empty():
    plugin = make_plugin(language="")
    assert plugin._plugin_config.language() == "zh-TW"


# ---------------------------------------------------------------------------
# _push_delay_seconds – defaults to 2, clamped 0-30
# ---------------------------------------------------------------------------
def test_push_delay_default():
    plugin = make_plugin()
    assert plugin._plugin_config.push_delay_seconds() == 2


def test_push_delay_clamped_max():
    plugin = make_plugin(push_delay_seconds=60)
    assert plugin._plugin_config.push_delay_seconds() == 30


def test_push_delay_clamped_min():
    plugin = make_plugin(push_delay_seconds=-5)
    assert plugin._plugin_config.push_delay_seconds() == 0


# ---------------------------------------------------------------------------
# _config_bool
# ---------------------------------------------------------------------------
def test_config_bool_true():
    plugin = make_plugin(test_key=True)
    assert plugin._config_bool("test_key", False) is True


def test_config_bool_string():
    plugin = make_plugin(test_key="true")
    assert plugin._config_bool("test_key", False) is True

    plugin = make_plugin(test_key="yes")
    assert plugin._config_bool("test_key", False) is True

    plugin = make_plugin(test_key="false")
    assert plugin._config_bool("test_key", True) is False


def test_config_bool_missing():
    plugin = make_plugin()
    assert plugin._config_bool("missing", True) is True
    assert plugin._config_bool("missing", False) is False


# ---------------------------------------------------------------------------
# _config_int – valid and fallback
# ---------------------------------------------------------------------------
def test_config_int_valid():
    plugin = make_plugin(test_key=42)
    assert plugin._plugin_config.config_int("test_key", 10) == 42


def test_config_int_invalid(caplog):
    caplog.set_level(logging.WARNING)
    plugin = make_plugin(test_key="abc")
    assert plugin._plugin_config.config_int("test_key", 10) == 10
    assert "配置 test_key 非法" in caplog.text


def test_config_int_missing():
    plugin = make_plugin()
    assert plugin._plugin_config.config_int("missing", 99) == 99
