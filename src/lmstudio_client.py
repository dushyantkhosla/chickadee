"""HTTP client for LM Studio REST API."""

import httpx

from src.exceptions import LMStudioError


class LMStudioClient:
    def __init__(self, base_url: str, model_key: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.model_key = model_key
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=10
        )

    async def is_reachable(self) -> bool:
        try:
            resp = await self._client.get("/api/v1/models")
            resp.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    async def is_model_loaded(self) -> bool:
        resp = await self._client.get("/api/v1/models")
        resp.raise_for_status()
        for model in resp.json().get("models", []):
            if model["key"] == self.model_key and model.get("loaded_instances"):
                return True
        return False

    async def ensure_model_loaded(self) -> str:
        if await self.is_model_loaded():
            return self.model_key
        try:
            resp = await self._client.post(
                "/api/v1/models/load", json={"model": self.model_key}
            )
            resp.raise_for_status()
            return self.model_key
        except httpx.HTTPStatusError as exc:
            raise LMStudioError(
                f"Failed to load model {self.model_key}: {exc.response.status_code}"
            ) from exc

    async def list_models(self) -> list[dict]:
        resp = await self._client.get("/api/v1/models")
        resp.raise_for_status()
        return resp.json().get("models", [])
