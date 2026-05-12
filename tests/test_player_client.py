from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from player.player_client import PlayerClient, _player_headers


class TestPlayerHeaders:
    def test_with_cookie(self):
        headers = _player_headers("abc=1", "en", "29080")
        assert headers["Cookie"] == "abc=1"
        assert headers["x-language"] == "en"
        assert headers["x-channel-type"] == "2"
        assert '"intl_game_id":"29080"' in headers["x-common-params"]

    def test_without_cookie(self):
        headers = _player_headers("", "ja", "29080")
        assert "Cookie" not in headers
        assert headers["x-language"] == "ja"

    def test_game_id_in_common_params(self):
        headers = _player_headers("", "ko", "12345")
        assert '"intl_game_id":"12345"' in headers["x-common-params"]


# ── helpers ──────────────────────────────────────────────────────


def _mock_resp(json_data, status=200):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    return resp


def _client_with_post(json_data):
    mock = MagicMock(spec=httpx.AsyncClient)
    mock.post = AsyncMock(return_value=_mock_resp(json_data))
    return PlayerClient(mock)


def _ok_data(**extra):
    return {"code": 0, "msg": "ok", "data": extra.pop("data", {"key": "val", **extra})}


# ── fetch_progress ───────────────────────────────────────────────


class TestFetchProgress:
    @pytest.mark.asyncio
    async def test_success(self):
        client = _client_with_post(_ok_data())
        result = await client.fetch_progress("cookie=1")
        assert result == {"key": "val"}

    @pytest.mark.asyncio
    async def test_no_client(self):
        client = PlayerClient(None)
        with pytest.raises(RuntimeError, match="http client not ready"):
            await client.fetch_progress("cookie=1")

    @pytest.mark.asyncio
    async def test_http_error(self):
        mock = MagicMock(spec=httpx.AsyncClient)
        mock.post = AsyncMock(side_effect=httpx.HTTPStatusError("err", request=MagicMock(), response=MagicMock()))
        client = PlayerClient(mock)
        with pytest.raises(httpx.HTTPStatusError):
            await client.fetch_progress("cookie=1")

    @pytest.mark.asyncio
    async def test_not_dict(self):
        client = _client_with_post([1, 2])
        with pytest.raises(RuntimeError, match="返回结构异常"):
            await client.fetch_progress("cookie=1")

    @pytest.mark.asyncio
    async def test_error_code(self):
        client = _client_with_post({"code": 1001, "msg": "bad token"})
        with pytest.raises(RuntimeError, match="PLAYER_API_ERROR:1001:bad token"):
            await client.fetch_progress("cookie=1")

    @pytest.mark.asyncio
    async def test_missing_data(self):
        client = _client_with_post({"code": 0, "msg": "ok"})
        with pytest.raises(RuntimeError, match="缺少 data 字段"):
            await client.fetch_progress("cookie=1")


# ── fetch_characters ─────────────────────────────────────────────


class TestFetchCharacters:
    @pytest.mark.asyncio
    async def test_success(self):
        chars = [{"name_code": 101, "name": "Anis"}]
        data = {"code": 0, "msg": "ok", "data": {"characters": chars}}
        client = _client_with_post(data)
        result = await client.fetch_characters("cookie=1")
        assert result == chars

    @pytest.mark.asyncio
    async def test_no_client(self):
        client = PlayerClient(None)
        with pytest.raises(RuntimeError, match="http client not ready"):
            await client.fetch_characters("cookie=1")

    @pytest.mark.asyncio
    async def test_no_characters_field(self):
        client = _client_with_post({"code": 0, "msg": "ok", "data": {}})
        with pytest.raises(RuntimeError, match="缺少 characters 字段"):
            await client.fetch_characters("cookie=1")


# ── fetch_character_details ──────────────────────────────────────


class TestFetchCharacterDetails:
    @pytest.mark.asyncio
    async def test_success(self):
        details = [{"skill1_lv": 5}]
        effects = [{"id": 9001}]
        data = {
            "code": 0,
            "msg": "ok",
            "data": {"character_details": details, "state_effects": effects},
        }
        client = _client_with_post(data)
        result_d, result_e = await client.fetch_character_details("c=1", 84, [101])
        assert result_d == details
        assert result_e == effects

    @pytest.mark.asyncio
    async def test_no_effects(self):
        data = {"code": 0, "msg": "ok", "data": {"character_details": [{"skill1_lv": 5}]}}
        client = _client_with_post(data)
        result_d, result_e = await client.fetch_character_details("c=1", 84, [101])
        assert result_d == [{"skill1_lv": 5}]
        assert result_e == []

    @pytest.mark.asyncio
    async def test_no_client(self):
        client = PlayerClient(None)
        with pytest.raises(RuntimeError, match="http client not ready"):
            await client.fetch_character_details("c=1", 84, [101])

    @pytest.mark.asyncio
    async def test_error_code(self):
        client = _client_with_post({"code": 5001, "msg": "server error"})
        with pytest.raises(RuntimeError, match="PLAYER_API_ERROR:5001"):
            await client.fetch_character_details("c=1", 84, [101])
