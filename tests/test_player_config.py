import logging

from main import NikkeNewsPlugin


def make_plugin(**config) -> NikkeNewsPlugin:
    base = {
        "enabled": True,
        "player_reminder": {
            "enabled": False,
            "cookie": "cookie=abc",
            "daily_mission_remind_time": "21:00",
            "outpost_fullness_threshold_percent": 90,
        },
    }
    for key, value in config.items():
        if key == "player_data_enabled":
            base["player_reminder"]["enabled"] = value
        elif key == "player_data_cookie":
            base["player_reminder"]["cookie"] = value
        elif key == "player_daily_mission_remind_time":
            base["player_reminder"]["daily_mission_remind_time"] = value
        elif key == "player_outpost_threshold":
            base["player_reminder"]["outpost_fullness_threshold_percent"] = value
        elif key in {
            "mapping_language",
            "mapping_cache_ttl_hours",
            "auto_refresh_mapping",
            "show_character_portrait",
        }:
            base["player_reminder"][key] = value
        else:
            base[key] = value
    return NikkeNewsPlugin(context=None, config=base)


def test_player_data_disabled_by_default():
    plugin = make_plugin()
    assert plugin._plugin_config.player_data_enabled() is False


def test_player_daily_remind_time_invalid(caplog):
    caplog.set_level(logging.WARNING)
    plugin = make_plugin(player_data_enabled=True, player_daily_mission_remind_time="bad")
    result = plugin._plugin_config.player_daily_mission_remind_time()
    assert result.hour == 21
    assert result.minute == 0
    assert "玩家提醒时间配置无效" in caplog.text


def test_player_daily_remind_time_valid():
    plugin = make_plugin(player_data_enabled=True, player_daily_mission_remind_time="18:30")
    result = plugin._plugin_config.player_daily_mission_remind_time()
    assert result.hour == 18
    assert result.minute == 30


def test_outpost_threshold_clamped():
    plugin = make_plugin(player_outpost_threshold=150)
    assert plugin._plugin_config.outpost_fullness_threshold_percent() == 100
    plugin = make_plugin(player_outpost_threshold=-5)
    assert plugin._plugin_config.outpost_fullness_threshold_percent() == 0


def test_player_mapping_defaults_and_clamps():
    plugin = make_plugin()
    assert plugin._plugin_config.player_mapping_language() == "en"
    assert plugin._plugin_config.player_mapping_cache_ttl_hours() == 168
    assert plugin._plugin_config.player_auto_refresh_mapping() is True

    plugin = make_plugin(mapping_language="bad", mapping_cache_ttl_hours=-3)
    assert plugin._plugin_config.player_mapping_language() == "en"
    assert plugin._plugin_config.player_mapping_cache_ttl_hours() == 1


def test_show_character_portrait_default():
    plugin = make_plugin()
    assert plugin._plugin_config.show_character_portrait() is True


def test_show_character_portrait_false():
    plugin = make_plugin(show_character_portrait=False)
    assert plugin._plugin_config.show_character_portrait() is False
