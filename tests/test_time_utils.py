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
    assert (
        is_cookie_invalid_error(RuntimeError("PLAYER_API_ERROR:401:bad cookie")) is True
    )


def test_is_cookie_invalid_error_plain_401_not_matched():
    """Plain Exception with '401' in message is NOT a cookie error (false positive)."""
    assert is_cookie_invalid_error(Exception("HTTP 401 unauthorized")) is False


def test_is_cookie_invalid_error_plain_cookie_not_matched():
    """Plain Exception with 'cookie' in message is NOT a cookie error (false positive)."""
    assert is_cookie_invalid_error(Exception("invalid cookie header")) is False


def test_is_cookie_invalid_error_httpx_401():
    import httpx
    from unittest.mock import MagicMock

    resp = MagicMock()
    resp.status_code = 401
    exc = httpx.HTTPStatusError("401", request=MagicMock(), response=resp)
    assert is_cookie_invalid_error(exc) is True


def test_is_cookie_invalid_error_httpx_403():
    import httpx
    from unittest.mock import MagicMock

    resp = MagicMock()
    resp.status_code = 403
    exc = httpx.HTTPStatusError("403", request=MagicMock(), response=resp)
    assert is_cookie_invalid_error(exc) is True


def test_is_cookie_invalid_error_httpx_500_not_matched():
    import httpx
    from unittest.mock import MagicMock

    resp = MagicMock()
    resp.status_code = 500
    exc = httpx.HTTPStatusError("500", request=MagicMock(), response=resp)
    assert is_cookie_invalid_error(exc) is False


def test_is_cookie_invalid_error_no_match():
    assert is_cookie_invalid_error(RuntimeError("connection refused")) is False
