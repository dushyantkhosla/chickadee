import pytest
import httpx

from src.lmstudio_client import LMStudioClient
from src.exceptions import LMStudioError


MOCK_BASE_URL = "http://test:1234/v1"
MOCK_MODEL_KEY = "test/model"


@pytest.fixture
def client():
    return LMStudioClient(MOCK_BASE_URL, MOCK_MODEL_KEY)


class TestIsReachable:
    @pytest.mark.asyncio
    async def test_returns_true_on_200(self, client, httpx_mock):
        httpx_mock.add_response(url=f"{MOCK_BASE_URL}/api/v1/models", json={"models": []})
        assert await client.is_reachable() is True

    @pytest.mark.asyncio
    async def test_returns_false_on_connection_error(self, client, httpx_mock):
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        assert await client.is_reachable() is False


class TestIsModelLoaded:
    @pytest.mark.asyncio
    async def test_returns_true_when_model_loaded(self, client, httpx_mock):
        httpx_mock.add_response(
            url=f"{MOCK_BASE_URL}/api/v1/models",
            json={"models": [{"key": MOCK_MODEL_KEY, "loaded_instances": [{"id": "x"}]}]},
        )
        assert await client.is_model_loaded() is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_loaded(self, client, httpx_mock):
        httpx_mock.add_response(
            url=f"{MOCK_BASE_URL}/api/v1/models",
            json={"models": [{"key": MOCK_MODEL_KEY, "loaded_instances": []}]},
        )
        assert await client.is_model_loaded() is False


class TestEnsureModelLoaded:
    @pytest.mark.asyncio
    async def test_already_loaded_returns_key(self, client, httpx_mock):
        httpx_mock.add_response(
            url=f"{MOCK_BASE_URL}/api/v1/models",
            json={"models": [{"key": MOCK_MODEL_KEY, "loaded_instances": [{"id": "x"}]}]},
        )
        result = await client.ensure_model_loaded()
        assert result == MOCK_MODEL_KEY

    @pytest.mark.asyncio
    async def test_loads_when_not_loaded(self, client, httpx_mock):
        httpx_mock.add_response(
            url=f"{MOCK_BASE_URL}/api/v1/models",
            json={"models": [{"key": MOCK_MODEL_KEY, "loaded_instances": []}]},
        )
        httpx_mock.add_response(
            url=f"{MOCK_BASE_URL}/api/v1/models/load",
            json={"status": "loaded", "instance_id": MOCK_MODEL_KEY},
        )
        result = await client.ensure_model_loaded()
        assert result == MOCK_MODEL_KEY

    @pytest.mark.asyncio
    async def test_raises_on_load_failure(self, client, httpx_mock):
        httpx_mock.add_response(
            url=f"{MOCK_BASE_URL}/api/v1/models",
            json={"models": [{"key": MOCK_MODEL_KEY, "loaded_instances": []}]},
        )
        httpx_mock.add_response(
            url=f"{MOCK_BASE_URL}/api/v1/models/load",
            status_code=500,
            text="internal error",
        )
        with pytest.raises(LMStudioError):
            await client.ensure_model_loaded()
