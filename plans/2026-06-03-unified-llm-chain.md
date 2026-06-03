# Unified LLM Chain — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge chickadee's two branches into a unified architecture with a 3-tier LLM fallback chain (LM Studio → Vercel paid → free pool) and Docker deployment.

**Architecture:** The agent layer (`agent.py`) delegates all LLM calls to a provider chain (`chain.py`). The chain tries providers in priority order: LM Studio on the laptop (when reachable, free) → Vercel AI Gateway (`openai/gpt-oss-20b`, $5/mo free tier) → free pool (Ollama, Groq, Cerebras, OpenRouter free models). Each provider returns a PydanticAI `Agent` instance; the chain catches exceptions and falls through. YouTube transcription stays cloud-only via OpenRouter multimodal (from `main` branch). Docker setup ported from `feat/docker-remote-lmstudio`.

**Tech Stack:** Python 3.13, PydanticAI (OpenAI-compatible), httpx, yt-dlp, trafilatura, python-telegram-bot, Docker

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/lmstudio_client.py` | **Create** (replaces `lmstudio_utils.py`) | Async HTTP client for LM Studio REST API — health check, model load status |
| `src/providers.py` | **Create** | Provider config registry, `ModelEntry` dataclass, provider resolution from env vars |
| `src/chain.py` | **Create** | `resolve_chain(mode)` iterator, `call_with_fallback()` — tries providers in order |
| `src/agent.py` | **Modify** | Refactor `classify()` and `summarise()` to use `call_with_fallback()` instead of direct LM Studio |
| `src/config.py` | **Modify** | Add Vercel, Groq, Cerebras, Ollama, OpenRouter env vars; remove `ANTHROPIC_API_KEY` |
| `src/main.py` | **Modify** | Remove `unload_model()` call (HTTP client doesn't need it), keep YouTube pipeline |
| `src/lmstudio_utils.py` | **Delete** | Replaced by `lmstudio_client.py` |
| `src/transcriber.py` | **Keep as-is** | YouTube audio → OpenRouter multimodal transcription |
| `src/fetcher.py` | **Keep as-is** | URL → text (YouTube via transcriber, others via trafilatura) |
| `src/models.py` | **Keep as-is** | Pydantic note schemas, routing tables |
| `src/renderer.py` | **Keep as-is** | AnyNote → Markdown |
| `src/vault.py` | **Keep as-is** | Filesystem writer |
| `src/vault_index.py` | **Keep as-is** | Cached vault title reader |
| `src/router.py` | **Keep as-is** | Domain-based ContentType detection |
| `src/bot.py` | **Keep as-is** | Telegram bot |
| `src/exceptions.py` | **Modify** | Add `LMStudioError`, `ProviderError` |
| `Dockerfile` | **Create** | Port from `feat/docker-remote-lmstudio` |
| `docker-compose.yml` | **Create** | Port from `feat/docker-remote-lmstudio` |
| `.dockerignore` | **Create** | Port from `feat/docker-remote-lmstudio` |
| `.env.example` | **Modify** | Document all new env vars |
| `pyproject.toml` | **Modify** | Add `vercel-ai-sdk` if needed (check if httpx suffices) |
| `tests/test_lmstudio_client.py` | **Create** | Test HTTP client with mocked httpx |
| `tests/test_providers.py` | **Create** | Test provider resolution, env var handling |
| `tests/test_chain.py` | **Create** | Test fallback chain logic with mocked providers |
| `tests/test_agent.py` | **Modify** | Update to test with mocked chain |
| `tests/conftest.py` | **Create** | Shared fixtures for mocked providers |

---

## Task 1: Branch Setup + Docker Infrastructure

**Files:**

- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: Create feature branch from main**

```bash
cd /Users/dush/Code/2026/chickadee
git checkout main
git checkout -b feat/unified-llm-chain
```

- [ ] **Step 2: Create Dockerfile**

Port from `feat/docker-remote-lmstudio`. Two-stage build: uv sync in builder, slim runtime.

```dockerfile
FROM python:3.13-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

FROM python:3.13-slim AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "src.bot"]
```

- [ ] **Step 3: Create docker-compose.yml**

```yaml
services:
  chickadee:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - /home/dushyant/code/chickadee/vault:/app/vault
```

- [ ] **Step 4: Create .dockerignore**

```
.venv/
.git/
.pytest_cache/
__pycache__/
*.pyc
.env
tests/
plans/
```

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: add Docker infrastructure for Pi deployment"
```

---

## Task 2: LM Studio HTTP Client

**Files:**

- Create: `src/lmstudio_client.py`
- Create: `tests/test_lmstudio_client.py`
- Delete: `src/lmstudio_utils.py`

- [ ] **Step 1: Write failing test for LMStudioClient**

```python
# tests/test_lmstudio_client.py
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from src.lmstudio_client import LMStudioClient


@pytest.fixture
def client():
    return LMStudioClient(
        base_url="http://192.168.1.52:1234/v1",
        model_key="gemma-4-e4b-it",
        api_key="",
    )


class TestIsReachable:
    async def test_returns_true_when_server_up(self, client):
        mock_response = httpx.Response(200, json={"models": []})
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_response):
            assert await client.is_reachable() is True

    async def test_returns_false_when_server_down(self, client):
        with patch.object(client._client, "get", new_callable=AsyncMock, side_effect=httpx.ConnectError("refused")):
            assert await client.is_reachable() is False

    async def test_returns_false_on_timeout(self, client):
        with patch.object(client._client, "get", new_callable=AsyncMock, side_effect=httpx.TimeoutException("timeout")):
            assert await client.is_reachable() is False


class TestIsModelLoaded:
    async def test_returns_true_when_model_loaded(self, client):
        mock_response = httpx.Response(200, json={
            "models": [
                {"key": "gemma-4-e4b-it", "loaded_instances": [{"id": "1"}]}
            ]
        })
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_response):
            assert await client.is_model_loaded() is True

    async def test_returns_false_when_model_not_loaded(self, client):
        mock_response = httpx.Response(200, json={
            "models": [
                {"key": "other-model", "loaded_instances": []}
            ]
        })
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_response):
            assert await client.is_model_loaded() is False


class TestEnsureModelLoaded:
    async def test_returns_immediately_if_already_loaded(self, client):
        with patch.object(client, "is_model_loaded", new_callable=AsyncMock, return_value=True):
            result = await client.ensure_model_loaded()
            assert result == "gemma-4-e4b-it"

    async def test_loads_model_if_not_loaded(self, client):
        mock_response = httpx.Response(200, json={})
        with patch.object(client, "is_model_loaded", new_callable=AsyncMock, return_value=False), \
             patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            result = await client.ensure_model_loaded()
            assert result == "gemma-4-e4b-it"
            mock_post.assert_called_once_with(
                "/api/v1/models/load", json={"model": "gemma-4-e4b-it"}
            )

    async def test_raises_on_load_failure(self, client):
        with patch.object(client, "is_model_loaded", new_callable=AsyncMock, return_value=False), \
             patch.object(client._client, "post", new_callable=AsyncMock,
                          side_effect=httpx.HTTPStatusError("500", request=httpx.Request("POST", "http://test"), response=httpx.Response(500))):
            with pytest.raises(Exception):
                await client.ensure_model_loaded()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/dush/Code/2026/chickadee
uv run pytest tests/test_lmstudio_client.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.lmstudio_client'`

- [ ] **Step 3: Create lmstudio_client.py**

Port from `feat/docker-remote-lmstudio` with async httpx client.

```python
"""HTTP client for LM Studio REST API."""

import logging

import httpx

from src.exceptions import LMStudioError

logger = logging.getLogger(__name__)


class LMStudioClient:
    """Async HTTP client for LM Studio's REST API.

    Handles health checking, model load status, and model loading.
    Used by the provider chain to determine if LM Studio is available.
    """

    def __init__(self, base_url: str, model_key: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.model_key = model_key
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=10.0
        )

    async def is_reachable(self) -> bool:
        """Check if LM Studio server is reachable. Returns False on any error."""
        try:
            resp = await self._client.get("/api/v1/models")
            resp.raise_for_status()
            return True
        except (httpx.HTTPError, httpx.TimeoutException):
            return False

    async def is_model_loaded(self) -> bool:
        """Check if the configured model is currently loaded."""
        resp = await self._client.get("/api/v1/models")
        resp.raise_for_status()
        for model in resp.json().get("models", []):
            if model["key"] == self.model_key and model.get("loaded_instances"):
                return True
        return False

    async def ensure_model_loaded(self) -> str:
        """Ensure model is loaded. Loads it if not. Returns model key."""
        if await self.is_model_loaded():
            return self.model_key
        try:
            resp = await self._client.post(
                "/api/v1/models/load", json={"model": self.model_key}
            )
            resp.raise_for_status()
            logger.info("Loaded model: %s", self.model_key)
            return self.model_key
        except httpx.HTTPStatusError as exc:
            raise LMStudioError(
                f"Failed to load model {self.model_key}: {exc.response.status_code}"
            ) from exc

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
```

- [ ] **Step 4: Add LMStudioError to exceptions.py**

```python
# src/exceptions.py — add to existing file

class LMStudioError(Exception):
    """Raised when LM Studio operations fail."""

class ProviderError(Exception):
    """Raised when all providers in the chain are exhausted."""
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_lmstudio_client.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 6: Delete lmstudio_utils.py and update imports**

```bash
rm src/lmstudio_utils.py
```

Remove the import from `src/agent.py` temporarily (will be fully refactored in Task 4):

```python
# src/agent.py — remove this line:
from src.lmstudio_utils import ensure_model_loaded, is_model_loaded, load_model
```

- [ ] **Step 7: Commit**

```bash
git add src/lmstudio_client.py src/exceptions.py tests/test_lmstudio_client.py
git rm src/lmstudio_utils.py
git commit -m "feat: replace subprocess lmstudio_utils with async HTTP lmstudio_client"
```

---

## Task 3: Provider Abstraction + Chain

**Files:**

- Create: `src/providers.py`
- Create: `src/chain.py`
- Create: `tests/test_providers.py`
- Create: `tests/test_chain.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write failing test for provider resolution**

```python
# tests/test_providers.py
import os
import pytest
from unittest.mock import patch

from src.providers import ModelEntry, ProviderConfig, PROVIDERS, resolve_provider


class TestProviderConfig:
    def test_get_models_from_env(self):
        config = ProviderConfig(
            name="test",
            api_key_env="TEST_KEY",
            provider_type="openai",
            base_url="http://test.com",
            models_env="TEST_MODELS",
            models_default="model-a,model-b",
        )
        with patch.dict(os.environ, {"TEST_MODELS": "model-x,model-y"}):
            assert config.get_models() == ["model-x", "model-y"]

    def test_get_models_from_default(self):
        config = ProviderConfig(
            name="test",
            api_key_env="TEST_KEY",
            provider_type="openai",
            base_url="http://test.com",
            models_env="TEST_MODELS",
            models_default="model-a,model-b",
        )
        with patch.dict(os.environ, {}, clear=True):
            assert config.get_models() == ["model-a", "model-b"]

    def test_returns_empty_when_no_key(self):
        config = ProviderConfig(
            name="test",
            api_key_env="MISSING_KEY",
            provider_type="openai",
            base_url="http://test.com",
            models_default="model-a",
        )
        with patch.dict(os.environ, {}, clear=True):
            entries = list(resolve_provider(config))
            assert entries == []


class TestResolveProvider:
    def test_yields_model_entries_for_valid_config(self):
        config = ProviderConfig(
            name="test",
            api_key_env="TEST_KEY",
            provider_type="openai",
            base_url="http://test.com",
            models_default="model-a,model-b",
        )
        with patch.dict(os.environ, {"TEST_KEY": "sk-test"}):
            entries = list(resolve_provider(config))
            assert len(entries) == 2
            assert all(isinstance(e, ModelEntry) for e in entries)
            assert entries[0].label.startswith("test:")
            assert entries[1].label.startswith("test:")

    def test_vercel_provider_type(self):
        config = ProviderConfig(
            name="vercel",
            api_key_env="VERCEL_KEY",
            provider_type="vercel",
            models_default="openai/gpt-oss-20b",
        )
        with patch.dict(os.environ, {"VERCEL_KEY": "test-key"}):
            entries = list(resolve_provider(config))
            assert len(entries) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_providers.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.providers'`

- [ ] **Step 3: Create providers.py**

```python
# src/providers.py
"""Provider registry and model entry resolution.

Based on dk-frugal-lm and dk-freellm patterns.
Each provider is a config entry that resolves to zero or more ModelEntry instances.
"""

import os
import random
from dataclasses import dataclass
from typing import Iterator

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.vercel import VercelProvider
from pydantic_ai.settings import ModelSettings


@dataclass
class ModelEntry:
    """A resolved model ready for use with PydanticAI Agent."""
    label: str                  # e.g. "vercel:openai/gpt-oss-20b"
    model: OpenAIChatModel
    settings: ModelSettings


@dataclass
class ProviderConfig:
    """Configuration for a single provider. Resolves to ModelEntry instances."""
    name: str
    api_key_env: str
    provider_type: str          # "openai" or "vercel"
    base_url: str | None = None
    models_env: str | None = None
    models_default: str = ""

    def get_models(self) -> list[str]:
        """Get model list from env var or default."""
        env_val = os.getenv(self.models_env or "") if self.models_env else ""
        models_str = env_val or self.models_default
        return [m.strip() for m in models_str.split(",") if m.strip()]


def _build_provider(base_url: str | None, api_key: str, provider_type: str):
    """Build a PydanticAI provider instance."""
    if provider_type == "vercel":
        return VercelProvider(api_key=api_key)
    return OpenAIProvider(base_url=base_url or "", api_key=api_key)


def resolve_provider(config: ProviderConfig, shuffle: bool = True) -> Iterator[ModelEntry]:
    """Resolve a provider config into ModelEntry instances.

    Yields nothing if the API key is not set.
    Shuffles models by default for load distribution.
    """
    api_key = os.getenv(config.api_key_env, "")
    if not api_key:
        return

    models = config.get_models()
    if shuffle:
        models = random.sample(models, len(models))

    for model_name in models:
        provider = _build_provider(config.base_url, api_key, config.provider_type)
        yield ModelEntry(
            label=f"{config.name}:{model_name}",
            model=OpenAIChatModel(model_name, provider=provider),
            settings=ModelSettings(timeout=30.0),
        )


# ── Provider registry ────────────────────────────────────────────────────────

PROVIDERS: dict[str, ProviderConfig] = {
    "vercel:paid": ProviderConfig(
        name="vercel",
        api_key_env="VERCEL_AI_GATEWAY_API_KEY",
        provider_type="vercel",
        models_env="VERCEL_PAID_MODEL",
        models_default="openai/gpt-oss-20b",
    ),
    "ollama": ProviderConfig(
        name="ollama",
        api_key_env="OLLAMA_API_KEY",
        provider_type="openai",
        base_url="https://ollama.com/v1",
        models_env="OLLAMA_MODELS",
        models_default="gemma4:31b,gpt-oss:20b",
    ),
    "groq": ProviderConfig(
        name="groq",
        api_key_env="GROQ_API_KEY",
        provider_type="openai",
        base_url="https://api.groq.com/openai/v1",
        models_env="GROQ_MODELS",
        models_default="openai/gpt-oss-120b",
    ),
    "cerebras": ProviderConfig(
        name="cerebras",
        api_key_env="CEREBRAS_API_KEY",
        provider_type="openai",
        base_url="https://api.cerebras.ai/v1",
        models_env="CEREBRAS_MODELS",
        models_default="gpt-oss-120b",
    ),
    "openrouter:free": ProviderConfig(
        name="openrouter",
        api_key_env="OPENROUTER_API_KEY",
        provider_type="openai",
        base_url="https://openrouter.ai/api/v1",
        models_env="OPENROUTER_FREE_MODELS",
        models_default="google/gemma-4-26b-a4b-it:free,google/gemma-4-31b-it:free,openai/gpt-oss-20b:free,openai/gpt-oss-120b:free",
    ),
}
```

- [ ] **Step 4: Run providers tests**

```bash
uv run pytest tests/test_providers.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Write failing test for chain**

```python
# tests/test_chain.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel

from src.chain import call_with_fallback, resolve_cloud_chain, resolve_full_chain
from src.providers import ModelEntry, ProviderConfig
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings


class DummyOutput(BaseModel):
    value: str


def _make_entry(label: str) -> ModelEntry:
    """Create a minimal ModelEntry for testing."""
    return ModelEntry(
        label=label,
        model=OpenAIChatModel("test-model", provider=OpenAIProvider(base_url="http://test", api_key="x")),
        settings=ModelSettings(timeout=5.0),
    )


class TestResolveCloudChain:
    def test_yields_vercel_first_then_free(self):
        """Vercel paid should come before free pool providers."""
        with patch.dict("os.environ", {
            "VERCEL_AI_GATEWAY_API_KEY": "test",
            "OPENROUTER_API_KEY": "test",
        }):
            entries = list(resolve_cloud_chain())
            labels = [e.label for e in entries]
            # Vercel entries should come before openrouter entries
            vercel_indices = [i for i, l in enumerate(labels) if l.startswith("vercel:")]
            free_indices = [i for i, l in enumerate(labels) if not l.startswith("vercel:")]
            if vercel_indices and free_indices:
                assert max(vercel_indices) < min(free_indices)


class TestResolveFullChain:
    def test_includes_lm_studio_when_reachable(self):
        lm_entry = _make_entry("lmstudio:gemma-4-e4b-it")
        with patch("src.chain._lm_studio_entry", return_value=lm_entry):
            entries = list(resolve_full_chain())
            assert entries[0].label == "lmstudio:gemma-4-e4b-it"

    def test_skips_lm_studio_when_unreachable(self):
        with patch("src.chain._lm_studio_entry", return_value=None):
            entries = list(resolve_full_chain())
            assert all(not e.label.startswith("lmstudio:") for e in entries)


class TestCallWithFallback:
    async def test_returns_first_success(self):
        entry = _make_entry("test:model")
        with patch("src.chain.resolve_full_chain", return_value=[entry]), \
             patch("src.chain.Agent") as MockAgent:
            mock_result = MagicMock()
            mock_result.output = DummyOutput(value="ok")
            MockAgent.return_value.run = AsyncMock(return_value=mock_result)
            result = await call_with_fallback(
                system_prompt="test",
                user_prompt="test",
                output_type=DummyOutput,
            )
            assert result == DummyOutput(value="ok")

    async def test_returns_none_when_all_fail(self):
        entry = _make_entry("test:model")
        with patch("src.chain.resolve_full_chain", return_value=[entry]), \
             patch("src.chain.Agent") as MockAgent:
            MockAgent.return_value.run = AsyncMock(side_effect=Exception("fail"))
            result = await call_with_fallback(
                system_prompt="test",
                user_prompt="test",
                output_type=DummyOutput,
            )
            assert result is None
```

- [ ] **Step 6: Run chain tests to verify they fail**

```bash
uv run pytest tests/test_chain.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.chain'`

- [ ] **Step 7: Create chain.py**

```python
# src/chain.py
"""LLM provider chain — tries providers in priority order.

Priority order:
1. LM Studio (laptop, when reachable) — free
2. Vercel AI Gateway (openai/gpt-oss-20b) — $5/mo free tier
3. Free pool (Ollama, Groq, Cerebras, OpenRouter free) — free

Usage:
    result = await call_with_fallback(
        system_prompt="...",
        user_prompt="...",
        output_type=MyModel,
    )
    if result is None:
        # all providers failed
"""

import logging
import os
from typing import Iterator, Type, TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent

from src.lmstudio_client import LMStudioClient
from src.providers import (
    PROVIDERS,
    ModelEntry,
    resolve_provider,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _lm_studio_entry() -> ModelEntry | None:
    """Build a ModelEntry for LM Studio if reachable. Returns None otherwise."""
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic_ai.settings import ModelSettings

    base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
    model_name = os.getenv("LM_STUDIO_MODEL", "gemma-4-e4b-it")
    api_key = os.getenv("LM_STUDIO_API_KEY", "")

    client = LMStudioClient(base_url, model_name, api_key)
    # Synchronous reachability check (blocking, but fast with short timeout)
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    # We need a sync check here since this is called from a sync iterator
    # Use httpx sync client for the probe
    import httpx
    try:
        with httpx.Client(timeout=3.0) as probe:
            resp = probe.get(f"{base_url}/models")
            resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException):
        return None

    provider = OpenAIProvider(base_url=base_url, api_key=api_key or "x")
    return ModelEntry(
        label=f"lmstudio:{model_name}",
        model=OpenAIChatModel(model_name, provider=provider),
        settings=ModelSettings(timeout=60.0),  # local models may be slower
    )


def resolve_full_chain() -> list[ModelEntry]:
    """Resolve the complete provider chain: LM Studio → Vercel → free pool."""
    entries: list[ModelEntry] = []

    # 1. LM Studio (if reachable)
    lm = _lm_studio_entry()
    if lm:
        entries.append(lm)
        logger.info("LM Studio reachable — added as primary provider")

    # 2. Cloud providers (Vercel paid → free pool)
    entries.extend(resolve_cloud_chain())

    return entries


def resolve_cloud_chain() -> list[ModelEntry]:
    """Resolve cloud-only providers: Vercel paid → free pool."""
    entries: list[ModelEntry] = []

    # Vercel paid (reliable, $5/mo budget)
    vercel_config = PROVIDERS.get("vercel:paid")
    if vercel_config:
        entries.extend(resolve_provider(vercel_config))

    # Free pool providers
    free_providers = ["ollama", "groq", "cerebras", "openrouter:free"]
    for name in free_providers:
        config = PROVIDERS.get(name)
        if config:
            entries.extend(resolve_provider(config))

    return entries


async def call_with_fallback(
    system_prompt: str,
    user_prompt: str,
    output_type: Type[T],
    max_retries: int = 3,
) -> T | None:
    """Try providers in chain order. Returns first success or None.

    Never raises — all exceptions are caught and logged.
    """
    for entry in resolve_full_chain():
        agent = Agent(
            model=entry.model,
            model_settings=entry.settings,
            output_type=output_type,
            instructions=system_prompt,
            retries=max_retries,
        )
        try:
            result = await agent.run(user_prompt)
            logger.info("Success with provider: %s", entry.label)
            return result.output
        except Exception as exc:
            logger.warning("Provider %s failed: %s", entry.label, exc)
            continue

    logger.error("All providers in chain exhausted")
    return None
```

- [ ] **Step 8: Run chain tests**

```bash
uv run pytest tests/test_chain.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 9: Commit**

```bash
git add src/providers.py src/chain.py tests/test_providers.py tests/test_chain.py tests/conftest.py
git commit -m "feat: add provider abstraction and 3-tier fallback chain"
```

---

## Task 4: Agent Refactor

**Files:**

- Modify: `src/agent.py`
- Modify: `tests/test_agent.py`

- [ ] **Step 1: Write failing test for refactored classify**

```python
# tests/test_agent.py — update existing tests
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pydantic import BaseModel

from src.agent import classify, summarise
from src.models import ContentType, ArticleNote


class TestClassify:
    async def test_returns_content_type_from_chain(self):
        with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = ContentType.article
            result = await classify("Some article text")
            assert result == ContentType.article
            mock_call.assert_called_once()

    async def test_falls_back_to_article_on_none(self):
        with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = None
            result = await classify("Some text")
            assert result == ContentType.article


class TestSummarise:
    async def test_calls_chain_with_correct_output_type(self):
        mock_note = MagicMock(spec=ArticleNote)
        with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_note
            result = await summarise(
                "Article text",
                ContentType.article,
                [],
                "https://example.com",
            )
            assert result == mock_note
```

- [ ] **Step 2: Run test to verify current tests still pass (baseline)**

```bash
uv run pytest tests/test_agent.py -v
```

Expected: Tests may fail because `lmstudio_utils` is deleted. This is expected — we're about to refactor.

- [ ] **Step 3: Refactor agent.py**

Replace the entire file. Key changes:
- Remove `lmstudio_utils` imports
- Remove direct LM Studio model creation
- Use `call_with_fallback()` for both classify and summarise
- Keep the same prompts and retry logic
- Keep `TalkMetadata` dataclass

```python
"""PydanticAI agents for classification and summarisation.

All LLM calls go through the provider chain (LM Studio → Vercel → free pool).
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from src.chain import call_with_fallback
from src.models import (
    AnyNote,
    ArticleNote,
    ContentType,
    EssayNote,
    FieldNote,
    PaperNote,
    RepoNote,
    TalkNote,
)

logger = logging.getLogger(__name__)

# ── Talk metadata (pre-populated from yt-dlp) ──────────────────────────────


@dataclass
class TalkMetadata:
    """Pre-populated metadata from yt-dlp. Passed as deps to the talk summariser."""
    title: str
    speaker: str
    categories: list[str]
    upload_date: Optional[date]


# ── Classifier ─────────────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM_PROMPT = """
You are a content classifier. Given an article's text, decide which of these
categories best describes the original piece:

- talk    : Conference talks, keynotes, podcasts, video lectures, presentations.
- article : Standard blog posts, journalism, news, how-to guides.
- paper   : Academic papers, preprints, research articles with IMRaD structure.
- essay   : Opinion pieces, long-form personal writing, Substack essays.
- repo    : GitHub repositories, code documentation, README-driven content.
- field   : Practitioner field reports: release notes, tool evals, benchmarks.

Respond with exactly one category. If uncertain, default to "article".
"""


async def classify(text: str) -> ContentType:
    """Classify article text into a ContentType.

    Falls back to ``ContentType.article`` if the LLM call fails.
    """
    result = await call_with_fallback(
        system_prompt=_CLASSIFIER_SYSTEM_PROMPT,
        user_prompt=text[:4000],
        output_type=ContentType,
        max_retries=3,
    )
    if result is None:
        logger.warning("Classification failed — all providers exhausted, defaulting to article")
        return ContentType.article
    return result


# ── Summariser ──────────────────────────────────────────────────────────────

_CONTENT_TYPE_TO_MODEL = {
    ContentType.talk: TalkNote,
    ContentType.article: ArticleNote,
    ContentType.paper: PaperNote,
    ContentType.essay: EssayNote,
    ContentType.repo: RepoNote,
    ContentType.field: FieldNote,
}


def _build_summariser_prompt(
    content_type: ContentType, vault_titles: list[str], url: str
) -> str:
    schema_name = _CONTENT_TYPE_TO_MODEL[content_type].__name__
    vault_section = ""
    if vault_titles:
        titles_text = "\n".join(f"- {t}" for t in vault_titles)
        vault_section = (
            f"Existing vault notes (exact titles):\n{titles_text}\n\n"
            "Populate builds_on, see_also, and contradicts using ONLY these exact titles. "
            "Leave empty if none match. Do not invent titles.\n"
        )
    return f"""You are a research assistant. Summarise the provided content into a structured {content_type.value} note.

Output must conform exactly to this Pydantic schema: {schema_name}

Rules:
- meta.source_url must be "{url}"
- meta.source_type must be "{content_type.value}"
- meta.ingested_on must be "{date.today().isoformat()}"
- meta.tags: kebab-case topic tags
- Reflection: always include a reflection object with individual fields set to null unless there is genuine insight. Do not set the entire reflection to null. Do not pad with generic text.
{vault_section}""".strip()


def _build_talk_prompt(vault_titles: list[str], url: str) -> str:
    """Simplified prompt for talk summarisation when metadata is pre-populated."""
    vault_section = ""
    if vault_titles:
        titles_text = "\n".join(f"- {t}" for t in vault_titles)
        vault_section = (
            f"Existing vault notes (exact titles):\n{titles_text}\n\n"
            "Populate builds_on, see_also, and contradicts using ONLY these exact titles. "
            "Leave empty if none match. Do not invent titles.\n"
        )
    return f"""You are a research assistant. Summarise the provided talk transcript into a structured talk note.

The title, speaker, and categories are provided via context — do NOT produce title or speaker fields.
Focus on: thesis, arguments, key_quotes, open_questions, and reflection.

Rules:
- meta.source_url must be "{url}"
- meta.source_type must be "talk"
- meta.ingested_on must be "{date.today().isoformat()}"
- meta.tags: kebab-case topic tags (seeded from the provided categories, refine as needed)
- Reflection: always include a reflection object with individual fields set to null unless there is genuine insight. Do not set the entire reflection to null. Do not pad with generic text.
{vault_section}""".strip()


async def summarise(
    text: str,
    content_type: ContentType,
    vault_titles: list[str],
    url: str,
    deps: TalkMetadata | None = None,
) -> AnyNote:
    """Summarise content into a typed *Note using the provider chain."""
    note_type = _CONTENT_TYPE_TO_MODEL[content_type]

    if content_type == ContentType.talk and deps is not None:
        prompt = _build_talk_prompt(vault_titles, url)
        # Inject metadata into the user prompt since we can't use RunContext
        # with the chain abstraction
        cats = ", ".join(deps.categories) if deps.categories else "none"
        meta_block = (
            f"\n\n---\n"
            f"Title: {deps.title}\n"
            f"Speaker: {deps.speaker}\n"
            f"Categories: {cats}\n"
            f"Upload date: {deps.upload_date.isoformat() if deps.upload_date else 'unknown'}"
        )
        user_prompt = text[:8000] + meta_block
    else:
        prompt = _build_summariser_prompt(content_type, vault_titles, url)
        user_prompt = text[:8000]

    result = await call_with_fallback(
        system_prompt=prompt,
        user_prompt=user_prompt,
        output_type=note_type,
        max_retries=3,
    )
    if result is None:
        raise RuntimeError(f"Summarisation failed — all providers exhausted for {url}")
    return result
```

- [ ] **Step 4: Update main.py to remove unload_model**

```python
# src/main.py — changes:
# 1. Remove: from src.lmstudio_utils import unload_model
# 2. Remove: the finally block with unload_model(settings.LM_STUDIO_MODEL)
# 3. Keep everything else (YouTube pipeline, TalkMetadata, etc.)

# The final run_pipeline should look like:
async def run_pipeline(url: str, dry_run: bool = False) -> tuple[Path | None, AnyNote]:
    """Full pipeline: fetch → route/classify → index → summarise → render → write."""
    print(f"Fetching {url} ...")
    text, yt_metadata = await fetch(url)
    print(f"Fetched {len(text.split())} words")

    content_type = await resolve_content_type(url, text)
    print(f"Resolved type: {content_type.value}")

    vault_titles = get_titles()
    print(f"Vault index: {len(vault_titles)} titles")

    # Build talk metadata from yt-dlp if available
    talk_deps = None
    if yt_metadata is not None and content_type == ContentType.talk:
        talk_deps = TalkMetadata(
            title=yt_metadata.title,
            speaker=yt_metadata.channel,
            categories=yt_metadata.categories,
            upload_date=_parse_upload_date(yt_metadata.upload_date),
        )

    note = await summarise(text, content_type, vault_titles, url, deps=talk_deps)

    # Inject upload_date into metadata if available
    if yt_metadata is not None:
        parsed_date = _parse_upload_date(yt_metadata.upload_date)
        if parsed_date:
            note.meta.upload_date = parsed_date

    title = getattr(note, "title", getattr(note, "name", "untitled"))
    print(f"Summarised: {title}")

    markdown = render(note)
    print(f"Rendered {len(markdown)} chars")

    if dry_run:
        print("\n--- DRY RUN ---\n")
        print(markdown)
        return None, note

    filename = make_filename(note_to_slug(note))
    path = write(filename, markdown)
    print(f"Written to {path}")
    return path, note
```

- [ ] **Step 5: Run all tests**

```bash
uv run pytest tests/ -v
```

Expected: All tests PASS. If `test_transcriber.py` fails, that's expected (OpenRouter API key not set in test env).

- [ ] **Step 6: Commit**

```bash
git add src/agent.py src/main.py tests/test_agent.py
git commit -m "feat: refactor agent to use provider chain, remove lmstudio_utils dependency"
```

---

## Task 5: Config + Environment

**Files:**

- Modify: `src/config.py`
- Modify: `.env.example`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Update config.py**

```python
"""Application settings loaded from environment / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Telegram ──────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    BOT_ALLOWED_CHAT_IDS: str = "*"

    # ── LM Studio (laptop, primary when available) ───────────────────────
    LM_STUDIO_BASE_URL: str = "http://localhost:1234/v1"
    LM_STUDIO_MODEL: str = "gemma-4-e4b-it"
    LM_STUDIO_API_KEY: str = ""

    # ── Vercel AI Gateway (paid, reliable fallback) ──────────────────────
    VERCEL_AI_GATEWAY_API_KEY: str = ""
    VERCEL_PAID_MODEL: str = "openai/gpt-oss-20b"

    # ── Free pool providers ──────────────────────────────────────────────
    OLLAMA_API_KEY: str = ""
    OLLAMA_MODELS: str = "gemma4:31b,gpt-oss:20b"

    GROQ_API_KEY: str = ""
    GROQ_MODELS: str = "openai/gpt-oss-120b"

    CEREBRAS_API_KEY: str = ""
    CEREBRAS_MODELS: str = "gpt-oss-120b"

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_FREE_MODELS: str = "google/gemma-4-26b-a4b-it:free,google/gemma-4-31b-it:free,openai/gpt-oss-20b:free,openai/gpt-oss-120b:free"

    # ── Transcription (YouTube audio → text via OpenRouter) ─────────────
    TRANSCRIPTION_MODEL: str = "xiaomi/mimo-v2.5"

    # ── Vault ────────────────────────────────────────────────────────────
    OBSIDIAN_VAULT_PATH: str = "/tmp/chickadee-vault"
    OBSIDIAN_API_KEY: str = ""
    OBSIDIAN_BASE_URL: str = ""


settings = Settings()
```

- [ ] **Step 2: Update .env.example**

```bash
# ── Telegram ──────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=
BOT_ALLOWED_CHAT_IDS=*

# ── LM Studio (laptop, primary when available) ───────────────────────────
LM_STUDIO_BASE_URL=http://192.168.1.52:1234/v1
LM_STUDIO_MODEL=gemma-4-e4b-it
LM_STUDIO_API_KEY=

# ── Vercel AI Gateway (paid, reliable fallback, $5/mo free tier) ─────────
VERCEL_AI_GATEWAY_API_KEY=
VERCEL_PAID_MODEL=openai/gpt-oss-20b

# ── Free pool (fallback when Vercel credits exhausted) ───────────────────
OLLAMA_API_KEY=
OLLAMA_MODELS=gemma4:31b,gpt-oss:20b

GROQ_API_KEY=
GROQ_MODELS=openai/gpt-oss-120b

CEREBRAS_API_KEY=
CEREBRAS_MODELS=gpt-oss-120b

OPENROUTER_API_KEY=
OPENROUTER_FREE_MODELS=google/gemma-4-26b-a4b-it:free,google/gemma-4-31b-it:free,openai/gpt-oss-20b:free,openai/gpt-oss-120b:free

# ── Transcription (YouTube audio → text) ─────────────────────────────────
TRANSCRIPTION_MODEL=xiaomi/mimo-v2.5

# ── Vault ────────────────────────────────────────────────────────────────
OBSIDIAN_VAULT_PATH=/tmp/chickadee-vault
```

- [ ] **Step 3: Update pyproject.toml if needed**

Check if `vercel-ai-sdk` is needed or if `httpx` + `pydantic-ai-slim[openai]` suffice. The `VercelProvider` is part of `pydantic-ai`. Check:

```bash
uv run python -c "from pydantic_ai.providers.vercel import VercelProvider; print('OK')"
```

If it fails, add the dependency:

```toml
[project]
dependencies = [
    # ... existing deps ...
    "pydantic-ai-slim[openai,vercel]>=1.89.1",  # add vercel extra
]
```

- [ ] **Step 4: Write test for config**

```python
# tests/test_config.py — update existing
import os
import pytest
from unittest.mock import patch


class TestSettings:
    def test_default_lm_studio_model(self):
        with patch.dict(os.environ, {}, clear=True):
            from src.config import Settings
            s = Settings()
            assert s.LM_STUDIO_MODEL == "gemma-4-e4b-it"

    def test_vercel_model_default(self):
        with patch.dict(os.environ, {}, clear=True):
            from src.config import Settings
            s = Settings()
            assert s.VERCEL_PAID_MODEL == "openai/gpt-oss-20b"
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/config.py .env.example tests/test_config.py pyproject.toml uv.lock
git commit -m "feat: update config with all provider env vars"
```

---

## Task 6: Integration Verification

**Files:**

- Create: `tests/test_integration.py` (update existing)

- [ ] **Step 1: Write integration test with all providers mocked**

```python
# tests/test_integration.py
"""Integration test: full pipeline with mocked providers."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from src.models import ArticleNote, ContentType, ObsidianMetadata, Reflection
from datetime import date


@pytest.fixture
def sample_article_note():
    return ArticleNote(
        meta=ObsidianMetadata(
            tags=["test"],
            source_url="https://example.com/article",
            source_type=ContentType.article,
            ingested_on=date.today(),
        ),
        title="Test Article",
        author="Test Author",
        thesis="This is a test thesis.",
        key_points=["Point 1", "Point 2"],
        evidence=["Evidence 1"],
        open_questions=[],
        reflection=Reflection(my_take="Interesting", so_what="Matters for testing", now_what="Write more tests"),
    )


class TestPipeline:
    async def test_full_pipeline_with_mocked_providers(self, sample_article_note, tmp_path):
        """Test the full pipeline with mocked fetch, classify, and summarise."""
        with patch("src.main.fetch", new_callable=AsyncMock) as mock_fetch, \
             patch("src.main.classify", new_callable=AsyncMock) as mock_classify, \
             patch("src.main.summarise", new_callable=AsyncMock) as mock_summarise, \
             patch("src.main.get_titles", return_value=[]), \
             patch("src.main.write") as mock_write, \
             patch("src.main.settings") as mock_settings:

            mock_fetch.return_value = ("Article text content", None)
            mock_classify.return_value = ContentType.article
            mock_summarise.return_value = sample_article_note
            mock_write.return_value = tmp_path / "test.md"
            mock_settings.OBSIDIAN_VAULT_PATH = str(tmp_path)

            from src.main import run_pipeline
            path, note = await run_pipeline("https://example.com/article")

            assert note.title == "Test Article"
            mock_fetch.assert_called_once()
            mock_classify.assert_called_once()
            mock_summarise.assert_called_once()
```

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: All tests PASS (except possibly `test_transcriber.py` which needs API keys).

- [ ] **Step 3: Run a dry-run to verify the pipeline structure**

```bash
# This will fail without a real LM Studio, but it should get past the import/structure checks
uv run python -c "
from src.config import settings
from src.providers import PROVIDERS, resolve_provider
from src.chain import resolve_cloud_chain, resolve_full_chain
from src.agent import classify, summarise
print('All imports OK')
print(f'Providers: {list(PROVIDERS.keys())}')
print(f'Vercel model: {settings.VERCEL_PAID_MODEL}')
print(f'LM Studio model: {settings.LM_STUDIO_MODEL}')
"
```

Expected: Prints import confirmation and provider list without errors.

- [ ] **Step 4: Final commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration test for unified pipeline"
```

---

## Task 7: Cleanup + Documentation

**Files:**

- Modify: `AGENTS.md`
- Modify: `DESIGN.md`
- Modify: `README.md`

- [ ] **Step 1: Update AGENTS.md with new architecture**

Update the "Architecture" section to describe the 3-tier fallback chain, the provider registry, and the file responsibilities.

- [ ] **Step 2: Update DESIGN.md**

Update the "Model Chain" section with the new priority order:
1. LM Studio (laptop) — `gemma-4-e4b-it`
2. Vercel (paid) — `openai/gpt-oss-20b`
3. Free pool — 8 models across 4 providers

- [ ] **Step 3: Update README.md**

Add Docker deployment instructions:
```bash
docker compose up -d
```

Add environment variable documentation.

- [ ] **Step 4: Final commit**

```bash
git add AGENTS.md DESIGN.md README.md
git commit -m "docs: update architecture docs for unified LLM chain"
```

---

## Summary: Provider Chain

```
URL received
    │
    ├── YouTube? ──→ yt-dlp download ──→ OpenRouter multimodal transcription
    │                                      (always cloud, $OPENROUTER_API_KEY)
    │
    └── Other ──→ httpx + trafilatura
                    │
                    ▼
              Domain routing (UNAMBIGUOUS_DOMAINS)
                    │
                    ├── Matched? ──→ ContentType
                    │
                    └── Unknown? ──→ LLM classify ──→ ContentType
                              │
                              ▼
                    LLM summarise ──→ AnyNote
                              │
                              ├── Provider chain:
                              │   1. LM Studio (gemma-4-e4b-it, laptop)
                              │   2. Vercel (openai/gpt-oss-20b, $5/mo)
                              │   3. Free pool (Ollama, Groq, Cerebras, OpenRouter)
                              │
                              ▼
                    Render Markdown ──→ Write to vault
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Telegram bot token |
| `LM_STUDIO_BASE_URL` | No | `http://localhost:1234/v1` | LM Studio API endpoint |
| `LM_STUDIO_MODEL` | No | `gemma-4-e4b-it` | Model to use on LM Studio |
| `LM_STUDIO_API_KEY` | No | `""` | LM Studio API key (if set) |
| `VERCEL_AI_GATEWAY_API_KEY` | Yes* | — | Vercel AI Gateway key |
| `VERCEL_PAID_MODEL` | No | `openai/gpt-oss-20b` | Vercel paid model |
| `OPENROUTER_API_KEY` | Yes* | — | For transcription + free pool |
| `OLLAMA_API_KEY` | No | — | Ollama Cloud key |
| `GROQ_API_KEY` | No | — | Groq API key |
| `CEREBRAS_API_KEY` | No | — | Cerebras API key |
| `OBSIDIAN_VAULT_PATH` | No | `/tmp/chickadee-vault` | Vault directory |

*At least one of `VERCEL_AI_GATEWAY_API_KEY` or `OPENROUTER_API_KEY` is needed for the cloud fallback to work.
