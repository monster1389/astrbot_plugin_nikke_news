from datetime import datetime

from core.time_utils import day_key, is_cookie_invalid_error


def test_day_key_before_4am():
    assert day_key(datetime(2024, 6, 3, 3, 59)) == "2024-06-02"


def test_day_key_at_4am():
    assert day_key(datetime(2024, 6, 3, 4, 0)) == "2024-06-03"


def test_day_key_after_4am():
    assert day_key(datetime(2024, 6, 3, 5, 0)) == "2024-06-03"


def test_day_key_midnight():
    assert day_key(datetime(2024, 6, 3, 0, 0)) == "2024-06-02"


def test_day_key_noon():
    assert day_key(datetime(2024, 12, 31, 12, 0)) == "2024-12-31"


def test_is_cookie_invalid_error_player_api():
    assert is_cookie_invalid_error(RuntimeError("PLAYER_API_ERROR:401:bad cookie")) is True


def test_is_cookie_invalid_error_401():
    assert is_cookie_invalid_error(Exception("HTTP 401 unauthorized")) is True


def test_is_cookie_invalid_error_cookie():
    assert is_cookie_invalid_error(Exception("invalid cookie header")) is True


def test_is_cookie_invalid_error_no_match():
    assert is_cookie_invalid_error(RuntimeError("connection refused")) is False
