import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from src.lmstudio_client import LMStudioClient


@pytest.fixture
def client():
    return LMStudioClient(
        base_url="http://192.168.1.52:1234/v1",
        model_key="gemma-4-e4b-it",
        api_key="",
    )


def _make_response(status_code: int, json_data: dict) -> httpx.Response:
    """Helper to create a properly initialized httpx.Response with request."""
    response = httpx.Response(status_code, json=json_data)
    response._request = httpx.Request("GET", "http://test")
    return response


class TestIsReachable:
    @pytest.mark.asyncio
    async def test_returns_true_when_server_up(self, client):
        mock_response = _make_response(200, {"models": []})
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_response):
            assert await client.is_reachable() is True

    @pytest.mark.asyncio
    async def test_returns_false_when_server_down(self, client):
        with patch.object(client._client, "get", new_callable=AsyncMock, side_effect=httpx.ConnectError("refused")):
            assert await client.is_reachable() is False

    @pytest.mark.asyncio
    async def test_returns_false_on_timeout(self, client):
        with patch.object(client._client, "get", new_callable=AsyncMock, side_effect=httpx.TimeoutException("timeout")):
            assert await client.is_reachable() is False


class TestIsModelLoaded:
    @pytest.mark.asyncio
    async def test_returns_true_when_model_loaded(self, client):
        mock_response = _make_response(200, {
            "models": [
                {"key": "gemma-4-e4b-it", "loaded_instances": [{"id": "1"}]}
            ]
        })
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_response):
            assert await client.is_model_loaded() is True

    @pytest.mark.asyncio
    async def test_returns_false_when_model_not_loaded(self, client):
        mock_response = _make_response(200, {
            "models": [
                {"key": "other-model", "loaded_instances": []}
            ]
        })
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_response):
            assert await client.is_model_loaded() is False


class TestEnsureModelLoaded:
    @pytest.mark.asyncio
    async def test_returns_immediately_if_already_loaded(self, client):
        with patch.object(client, "is_model_loaded", new_callable=AsyncMock, return_value=True):
            result = await client.ensure_model_loaded()
            assert result == "gemma-4-e4b-it"

    @pytest.mark.asyncio
    async def test_loads_model_if_not_loaded(self, client):
        mock_response = _make_response(200, {})
        with patch.object(client, "is_model_loaded", new_callable=AsyncMock, return_value=False), \
             patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            result = await client.ensure_model_loaded()
            assert result == "gemma-4-e4b-it"
            mock_post.assert_called_once_with(
                "/api/v1/models/load", json={"model": "gemma-4-e4b-it"}
            )

    @pytest.mark.asyncio
    async def test_raises_on_load_failure(self, client):
        with patch.object(client, "is_model_loaded", new_callable=AsyncMock, return_value=False), \
             patch.object(client._client, "post", new_callable=AsyncMock,
                          side_effect=httpx.HTTPStatusError("500", request=httpx.Request("POST", "http://test"), response=httpx.Response(500))):
            with pytest.raises(Exception):
                await client.ensure_model_loaded()
