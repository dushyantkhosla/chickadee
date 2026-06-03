# FallbackModel + RunContext Deps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-rolled provider chain in `src/chain.py` with PydanticAI's `FallbackModel`, and restore the typed `RunContext[TalkMetadata]` dependency flow in `src/agent.py` that was lost in the prior `chain.py` refactor.

**Architecture:** `chain.py` becomes a thin shim: it builds a `FallbackModel` from a flat `list[Model]` (resolved from providers, with an LM Studio reachability probe gating the laptop tier), constructs the `Agent` with optional `deps_type` and an optional `setup` callback, and wraps `agent.run()` in `try/except → None`. `agent.py` uses the `setup` callback to attach `@agent.instructions` that inject `TalkMetadata` into the **system channel** via `RunContext`, replacing the previous user-prompt string-injection.

**Tech Stack:** Python 3.13, PydanticAI (`FallbackModel`, `RunContext`, `agent.instructions`), pytest, FunctionModel for system-message assertions.

**Spec:** `plans/2026-06-03-fallbackmodel-deps-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/providers.py` | Modify | `ProviderConfig`, `PROVIDERS` registry, `build_models(config) → list[Model]`. Delete `ModelEntry`, delete `resolve_provider`. |
| `src/chain.py` | Modify | `resolve_models()` list builder, `call_with_fallback` shim with `FallbackModel` + `setup` + deps validation. Delete `_lm_studio_entry`, `resolve_full_chain`, `resolve_cloud_chain`. |
| `src/agent.py` | Modify | Add `_inject_talk_metadata` and `_setup_talk_metadata` module-level functions. Update `summarise()` to use the `setup` callback. Remove user-prompt string injection of `TalkMetadata`. |
| `tests/test_providers.py` | Modify | Rename `TestResolveProvider` → `TestBuildModels`. Update existing tests for new API. |
| `tests/test_chain.py` | Modify | Restructure around `resolve_models`. Add tests for deps + setup + validation. |
| `tests/test_summariser.py` | Modify | Rewrite `test_summarise_talk_with_deps_injects_metadata` to assert new behavior. |
| `tests/test_integration.py` | No change | Mocks signature is unchanged. |

---

## Task 1: Slim `src/providers.py` — delete `ModelEntry`, add `build_models`

**Files:**
- Modify: `src/providers.py`
- Modify: `tests/test_providers.py`

- [ ] **Step 1: Write the failing test for `build_models`**

Replace `tests/test_providers.py:46-60` (`TestResolveProvider.test_yields_model_entries_for_valid_config`) with:

```python
class TestBuildModels:
    def test_yields_model_instances_for_valid_config(self):
        config = ProviderConfig(
            name="test",
            api_key_env="TEST_KEY",
            provider_type="openai",
            base_url="http://test.com",
            models_default="model-a,model-b",
        )
        with patch.dict(os.environ, {"TEST_KEY": "sk-test"}):
            models = build_models(config)
            assert len(models) == 2
            assert all(isinstance(m, OpenAIChatModel) for m in models)

    def test_vercel_provider_type(self):
        config = ProviderConfig(
            name="vercel",
            api_key_env="VERCEL_KEY",
            provider_type="vercel",
            models_default="openai/gpt-oss-20b",
        )
        with patch.dict(os.environ, {"VERCEL_KEY": "test-key"}):
            models = build_models(config)
            assert len(models) == 1
            assert isinstance(models[0], OpenAIChatModel)
```

Update the import at the top of `tests/test_providers.py` to add `build_models`:

```python
from src.providers import ModelEntry, ProviderConfig, PROVIDERS, build_models, resolve_provider
```

(Keep the `resolve_provider` import for now — it'll be removed in step 3.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_providers.py::TestBuildModels -v`
Expected: FAIL with `ImportError: cannot import name 'build_models' from 'src.providers'`

- [ ] **Step 3: Update `src/providers.py`**

Replace the contents of `src/providers.py` with:

```python
"""Provider registry and model entry resolution.

Each provider is a config entry that resolves to a list of PydanticAI Model
instances via build_models(). The list is consumed by chain.resolve_models().
"""

import os
import random
from dataclasses import dataclass

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.vercel import VercelProvider


@dataclass
class ProviderConfig:
    """Configuration for a single provider. Resolves to PydanticAI Model instances."""
    name: str
    api_key_env: str
    provider_type: str            # "openai" | "vercel"
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


def build_models(config: ProviderConfig, shuffle: bool = True) -> list[OpenAIChatModel]:
    """Build PydanticAI Model instances for this provider.

    Returns [] if the API key is not set. Shuffles models for load distribution.
    """
    api_key = os.getenv(config.api_key_env, "")
    if not api_key:
        return []

    models = config.get_models()
    if shuffle:
        random.shuffle(models)

    provider = _build_provider(config.base_url, api_key, config.provider_type)
    return [OpenAIChatModel(name, provider=provider) for name in models]


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

- [ ] **Step 4: Update the existing `test_returns_empty_when_no_key` to use `build_models`**

Replace `tests/test_providers.py:33-43` with:

```python
    def test_returns_empty_when_no_key(self):
        config = ProviderConfig(
            name="test",
            api_key_env="MISSING_KEY",
            provider_type="openai",
            base_url="http://test.com",
            models_default="model-a",
        )
        with patch.dict(os.environ, {}, clear=True):
            models = build_models(config)
            assert models == []
```

- [ ] **Step 5: Remove the now-stale import and run the suite**

In `tests/test_providers.py`, remove `resolve_provider` from the import line:

```python
from src.providers import ModelEntry, ProviderConfig, PROVIDERS, build_models
```

Run: `uv run pytest tests/test_providers.py -v`
Expected: 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/providers.py tests/test_providers.py
git commit -m "refactor(providers): drop ModelEntry, replace resolve_provider with build_models returning list[Model]"
```

---

## Task 2: Slim `src/chain.py` — list builder + `FallbackModel` shim

**Files:**
- Modify: `src/chain.py`
- Modify: `tests/test_chain.py`

- [ ] **Step 1: Write the failing tests for `resolve_models`**

Replace `tests/test_chain.py:41-52` (`TestResolveFullChain`) with:

```python
class TestResolveModels:
    def test_includes_lm_studio_when_reachable(self):
        from src.chain import _build_lm_studio_model
        lm_model = _build_lm_studio_model()
        with patch.dict("os.environ", {"LM_STUDIO_BASE_URL": "http://localhost:1234/v1"}), \
             patch("src.chain._lm_studio_reachable", return_value=True), \
             patch("src.chain.build_models", return_value=[]):
            models = resolve_models()
            assert models[0] is lm_model

    def test_skips_lm_studio_when_unreachable(self):
        with patch("src.chain._lm_studio_reachable", return_value=False), \
             patch("src.chain.build_models", return_value=[]):
            models = resolve_models()
            assert all(not isinstance(m, OpenAIChatModel) or m.model_name != "gemma-4-e4b-it" for m in models)

    def test_appends_cloud_providers_in_order(self):
        with patch("src.chain._lm_studio_reachable", return_value=False), \
             patch("src.chain.build_models") as mock_build:
            mock_build.side_effect = lambda cfg, **kw: [f"model-from-{cfg.name}"]
            models = resolve_models()
            # Vercel paid is queried first, then free pool providers
            called_names = [c.args[0].name for c in mock_build.call_args_list]
            assert "vercel" in called_names
            assert "ollama" in called_names
            assert "groq" in called_names
            assert "cerebras" in called_names
            assert "openrouter" in called_names
```

Update the imports at the top of `tests/test_chain.py` to add `resolve_models`:

```python
from src.chain import call_with_fallback, resolve_models
from src.providers import build_models
```

(Delete the import of `resolve_full_chain` and `resolve_cloud_chain` — they're gone.)

Also delete the `TestResolveCloudChain` class entirely (lines 25-39 in the current file). It's no longer relevant.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_chain.py::TestResolveModels -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_models' from 'src.chain'`

- [ ] **Step 3: Implement `resolve_models` and helpers in `src/chain.py`**

Replace the contents of `src/chain.py` with:

```python
"""LLM provider chain — resolves models and runs via PydanticAI FallbackModel.

Priority order:
1. LM Studio (laptop, when reachable) — free
2. Vercel AI Gateway (openai/gpt-oss-20b) — $5/mo free tier
3. Free pool (Ollama, Groq, Cerebras, OpenRouter free) — free

Usage:
    result = await call_with_fallback(
        system_prompt="...",
        user_prompt="...",
        output_type=MyModel,
        deps=my_deps,                 # optional
        deps_type=MyDeps,             # optional, required if deps is set
        setup=lambda agent: ...,      # optional, for @agent.instructions etc
    )
    if result is None:
        # all providers failed
"""

import logging
import os
from typing import Any, Callable, Type, TypeVar

import httpx
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.providers import PROVIDERS, build_models

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_CLOUD_PROVIDER_ORDER = ["vercel:paid", "ollama", "groq", "cerebras", "openrouter:free"]


def _lm_studio_reachable() -> bool:
    """Sync HTTP probe, 3s timeout. False on any error.

    Called from resolve_models() to decide whether to add LM Studio as the
    primary provider. A 3s timeout is short enough not to block the bot
    noticeably when the laptop is off, and long enough to tolerate a slow
    LM Studio cold start.
    """
    base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
    try:
        with httpx.Client(timeout=3.0) as probe:
            probe.get(f"{base_url.rstrip('/')}/models").raise_for_status()
        return True
    except (httpx.HTTPError, httpx.TimeoutException):
        return False


def _build_lm_studio_model() -> Model:
    base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
    model_name = os.getenv("LM_STUDIO_MODEL", "gemma-4-e4b-it")
    api_key = os.getenv("LM_STUDIO_API_KEY", "") or "x"
    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(base_url=base_url, api_key=api_key),
    )


def resolve_models() -> list[Model]:
    """Return the ordered model list. LM Studio first if reachable.

    The list is consumed by call_with_fallback() to build a FallbackModel.
    """
    models: list[Model] = []
    if _lm_studio_reachable():
        models.append(_build_lm_studio_model())
        logger.info("LM Studio reachable — added as primary provider")

    for name in _CLOUD_PROVIDER_ORDER:
        if config := PROVIDERS.get(name):
            models.extend(build_models(config))

    return models


async def call_with_fallback(
    system_prompt: str,
    user_prompt: str,
    output_type: Type[T],
    *,
    deps: Any = None,
    deps_type: type | None = None,
    setup: Callable[[Agent], None] | None = None,
    max_retries: int = 3,
) -> T | None:
    """Run via FallbackModel. Returns first success or None. Never raises.

    output_type is constrained to a Pydantic BaseModel subclass (never str);
    PydanticAI's default ToolOutput mode validates the response against the
    schema and retries up to max_retries on validation failure.

    deps and deps_type are paired: setting one requires the other.
    setup is an optional callback invoked after Agent construction but
    before run(); use it to attach @agent.instructions, @agent.tool, etc.
    """
    if deps is not None and deps_type is None:
        raise ValueError("deps provided without deps_type")
    if deps_type is not None and deps is None:
        raise ValueError("deps_type provided without deps")

    models = resolve_models()
    if not models:
        logger.error("No providers available — all env keys unset or LM Studio unreachable")
        return None

    agent_kwargs: dict = {
        "model": FallbackModel(*models),
        "output_type": output_type,
        "instructions": system_prompt,
        "retries": max_retries,
    }
    if deps_type is not None:
        agent_kwargs["deps_type"] = deps_type

    agent = Agent(**agent_kwargs)

    if setup is not None:
        setup(agent)

    run_kwargs: dict = {}
    if deps is not None:
        run_kwargs["deps"] = deps

    try:
        result = await agent.run(user_prompt, **run_kwargs)
        logger.info("Success on fallback chain")
        return result.output
    except Exception as exc:
        logger.error("All providers exhausted: %s", exc)
        return None
```

- [ ] **Step 4: Run `resolve_models` tests**

Run: `uv run pytest tests/test_chain.py::TestResolveModels -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Write the failing tests for `call_with_fallback` with `FallbackModel` and deps/validation**

Replace the existing `TestCallWithFallback` class (`tests/test_chain.py:54-80`) with:

```python
from datetime import date
from src.agent import TalkMetadata


class _MockModel:
    """Minimal stand-in for a PydanticAI Model, accepted by FallbackModel."""
    def __init__(self, model_name: str = "test-model"):
        self.model_name = model_name

    def __eq__(self, other):
        return isinstance(other, _MockModel) and other.model_name == self.model_name

    def __hash__(self):
        return hash(self.model_name)


class TestCallWithFallback:
    @pytest.mark.asyncio
    async def test_returns_first_success(self):
        with patch("src.chain.resolve_models", return_value=[_MockModel()]), \
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

    @pytest.mark.asyncio
    async def test_returns_none_when_all_fail(self):
        with patch("src.chain.resolve_models", return_value=[_MockModel()]), \
             patch("src.chain.Agent") as MockAgent:
            MockAgent.return_value.run = AsyncMock(side_effect=Exception("fail"))
            result = await call_with_fallback(
                system_prompt="test",
                user_prompt="test",
                output_type=DummyOutput,
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_providers(self):
        with patch("src.chain.resolve_models", return_value=[]):
            result = await call_with_fallback(
                system_prompt="test",
                user_prompt="test",
                output_type=DummyOutput,
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_raises_when_deps_set_without_deps_type(self):
        with pytest.raises(ValueError, match="deps provided without deps_type"):
            await call_with_fallback(
                "sp", "up", DummyOutput, deps="x"
            )

    @pytest.mark.asyncio
    async def test_raises_when_deps_type_set_without_deps(self):
        with pytest.raises(ValueError, match="deps_type provided without deps"):
            await call_with_fallback(
                "sp", "up", DummyOutput, deps_type=TalkMetadata
            )

    @pytest.mark.asyncio
    async def test_deps_passed_to_agent_run(self):
        deps = TalkMetadata(
            title="T", speaker="S", categories=[], upload_date=None
        )
        with patch("src.chain.resolve_models", return_value=[_MockModel()]), \
             patch("src.chain.Agent") as MockAgent:
            MockAgent.return_value.run = AsyncMock(
                return_value=MagicMock(output=DummyOutput(value="ok"))
            )
            await call_with_fallback(
                "sp", "up", DummyOutput,
                deps=deps, deps_type=TalkMetadata,
            )
            MockAgent.return_value.run.assert_awaited_with("up", deps=deps)

    @pytest.mark.asyncio
    async def test_no_deps_kwarg_when_deps_is_none(self):
        with patch("src.chain.resolve_models", return_value=[_MockModel()]), \
             patch("src.chain.Agent") as MockAgent:
            MockAgent.return_value.run = AsyncMock(
                return_value=MagicMock(output=DummyOutput(value="ok"))
            )
            await call_with_fallback("sp", "up", DummyOutput)
            MockAgent.return_value.run.assert_awaited_with("up")

    @pytest.mark.asyncio
    async def test_setup_callback_invoked_after_agent_construction(self):
        setup_called = []

        def my_setup(agent):
            setup_called.append(agent)

        with patch("src.chain.resolve_models", return_value=[_MockModel()]), \
             patch("src.chain.Agent") as MockAgent:
            MockAgent.return_value.run = AsyncMock(
                return_value=MagicMock(output=DummyOutput(value="ok"))
            )
            await call_with_fallback("sp", "up", DummyOutput, setup=my_setup)
            assert setup_called == [MockAgent.return_value]
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `uv run pytest tests/test_chain.py::TestCallWithFallback -v`
Expected: FAIL with `ImportError` on `_MockModel` (we added new symbols not yet imported) and `TypeError: unexpected keyword argument 'deps'` (call_with_fallback doesn't yet accept deps).

- [ ] **Step 7: Verify the implementation already accepts these (it does from Step 3)**

The implementation in Step 3 already supports all of this. No further code changes needed in this step. Run the tests:

Run: `uv run pytest tests/test_chain.py::TestCallWithFallback -v`
Expected: 8 tests PASS.

- [ ] **Step 8: Add a FunctionModel test that proves metadata reaches the system instructions**

Add to `tests/test_chain.py` after the `TestCallWithFallback` class:

```python
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart


class TestSetupCallbackAttachesInstructions:
    @pytest.mark.asyncio
    async def test_metadata_reaches_system_instructions_via_setup(self):
        from pydantic_ai import Agent, RunContext
        from src.agent import TalkMetadata

        captured: list[list[ModelMessage]] = []

        def fn_model(messages: list[ModelMessage], info) -> ModelResponse:
            captured.append(list(messages))
            return ModelResponse(parts=[TextPart("{}")])

        deps = TalkMetadata(
            title="The Talk Title",
            speaker="Dr. Speaker",
            categories=["ai", "ml"],
            upload_date=date(2026, 1, 15),
        )

        def setup(agent: Agent) -> None:
            @agent.instructions
            def inject(ctx: RunContext[TalkMetadata]) -> str:
                d = ctx.deps
                return f"Title: {d.title}\nSpeaker: {d.speaker}"

        with patch("src.chain.resolve_models", return_value=[_MockModel()]):
            # Build a real Agent in the test so we can verify instructions land
            # in the system message via FunctionModel.
            agent = Agent(
                model=FallbackModel(FunctionModel(fn_model)),
                deps_type=TalkMetadata,
                output_type=DummyOutput,
                instructions="Static instructions",
            )
            setup(agent)
            await agent.run("transcript", deps=deps)

        assert len(captured) == 1
        messages = captured[0]
        # The system prompt is the first message in the request.
        from pydantic_ai.messages import SystemPromptPart
        system_parts = [
            part.content
            for msg in messages
            for part in msg.parts
            if isinstance(part, SystemPromptPart)
        ]
        combined = "\n".join(system_parts)
        assert "The Talk Title" in combined
        assert "Dr. Speaker" in combined
        assert "Static instructions" in combined
```

Add `FallbackModel` to the imports at the top of `tests/test_chain.py`:

```python
from pydantic_ai.models.fallback import FallbackModel
```

- [ ] **Step 9: Run the full chain test suite**

Run: `uv run pytest tests/test_chain.py -v`
Expected: 3 (TestResolveModels) + 8 (TestCallWithFallback) + 1 (TestSetupCallbackAttachesInstructions) = 12 tests PASS.

- [ ] **Step 10: Commit**

```bash
git add src/chain.py tests/test_chain.py
git commit -m "refactor(chain): adopt FallbackModel, add setup callback + deps validation"
```

---

## Task 3: Restore `RunContext` deps in `src/agent.py`

**Files:**
- Modify: `src/agent.py`
- Modify: `tests/test_summariser.py`

- [ ] **Step 1: Rewrite the failing test for deps flow**

Replace `tests/test_summariser.py:179-204` (`test_summarise_talk_with_deps_injects_metadata`) with:

```python
@pytest.mark.asyncio
async def test_summarise_talk_with_deps_invokes_setup_callback():
    """When TalkMetadata is provided for a talk, summarise should call
    call_with_fallback with deps, deps_type, and a setup callback.
    The setup callback is what restores the RunContext instructions flow.
    """
    note = MagicMock()
    deps = TalkMetadata(
        title="Test Talk",
        speaker="Test Speaker",
        categories=["ai", "ml"],
        upload_date=date(2026, 1, 1),
    )
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = note
        result = await summarise(
            "Transcript text",
            ContentType.talk,
            [],
            "https://youtube.com/watch?v=123",
            deps=deps,
        )
        assert result == note
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs["deps"] is deps
        assert call_kwargs["deps_type"] is TalkMetadata
        assert callable(call_kwargs["setup"])
        # User prompt no longer contains the metadata string-injection.
        assert "Test Talk" not in call_kwargs["user_prompt"]
        assert "Test Speaker" not in call_kwargs["user_prompt"]


@pytest.mark.asyncio
async def test_summarise_non_talk_does_not_pass_deps():
    """Non-talk notes should not pass deps or setup to the chain."""
    note = MagicMock()
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = note
        await summarise("text", ContentType.article, [], "https://example.com")
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs["deps"] is None
        assert call_kwargs["deps_type"] is None
        assert call_kwargs["setup"] is None


@pytest.mark.asyncio
async def test_summarise_talk_without_deps_does_not_pass_deps():
    """A talk with no deps should not pass deps or setup."""
    note = MagicMock()
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = note
        await summarise("text", ContentType.talk, [], "https://example.com")
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs["deps"] is None
        assert call_kwargs["deps_type"] is None
        assert call_kwargs["setup"] is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_summariser.py -v -k "deps or non_talk"`
Expected: 3 tests FAIL (the existing `test_summarise_talk_with_deps_injects_metadata` and the two new ones, because `call_with_fallback` mock will not yet receive the new kwargs).

- [ ] **Step 3: Add module-level helpers and update `summarise()` in `src/agent.py`**

Replace the section from `def _build_talk_prompt` to the end of `summarise()` (currently `src/agent.py:108-166`) with:

```python
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


def _inject_talk_metadata(ctx: RunContext[TalkMetadata]) -> str:
    """System-channel injection of talk metadata. PydanticAI concatenates
    this with the static instructions and sends it as the system message,
    so the LLM treats it as authoritative rather than as user data.
    """
    d = ctx.deps
    cats = ", ".join(d.categories) if d.categories else "none"
    return (
        f"Title: {d.title}\n"
        f"Speaker: {d.speaker}\n"
        f"Categories: {cats}\n"
        f"Upload date: {d.upload_date.isoformat() if d.upload_date else 'unknown'}"
    )


def _setup_talk_metadata(agent: Agent) -> None:
    """Attach the @agent.instructions callback that injects TalkMetadata
    via RunContext. Called by call_with_fallback after Agent construction
    but before agent.run().
    """
    agent.instructions(_inject_talk_metadata)


async def summarise(
    text: str,
    content_type: ContentType,
    vault_titles: list[str],
    url: str,
    deps: TalkMetadata | None = None,
) -> AnyNote:
    """Summarise content into a typed *Note using the provider chain.

    For talk notes with deps, attach _inject_talk_metadata to the Agent
    via the setup callback so TalkMetadata flows through the system channel
    via RunContext. For all other calls, the Agent has no deps.
    """
    note_type = _CONTENT_TYPE_TO_MODEL[content_type]

    if content_type == ContentType.talk and deps is not None:
        prompt = _build_talk_prompt(vault_titles, url)
    else:
        prompt = _build_summariser_prompt(content_type, vault_titles, url)

    user_prompt = text[:8000]
    use_deps = content_type == ContentType.talk and deps is not None

    result = await call_with_fallback(
        system_prompt=prompt,
        user_prompt=user_prompt,
        output_type=note_type,
        deps=deps if use_deps else None,
        deps_type=TalkMetadata if use_deps else None,
        setup=_setup_talk_metadata if use_deps else None,
        max_retries=3,
    )
    if result is None:
        raise RuntimeError(f"Summarisation failed — all providers exhausted for {url}")
    return result
```

Also update the import block at the top of `src/agent.py` to add `RunContext` and `Agent`:

```python
from pydantic_ai import Agent, RunContext
```

(Remove the now-stale comment on `agent.py:144` about "can't use RunContext with chain abstraction" — the chain now supports it.)

- [ ] **Step 4: Run the test suite**

Run: `uv run pytest tests/test_summariser.py -v`
Expected: All tests PASS, including the 3 new/rewritten ones.

- [ ] **Step 5: Commit**

```bash
git add src/agent.py tests/test_summariser.py
git commit -m "refactor(agent): restore RunContext[TalkMetadata] deps flow via setup callback"
```

---

## Task 4: Full test suite + manual verification

**Files:** None (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: ~106 tests PASS. If `test_transcriber.py` fails, that's expected (OpenRouter API key not set in test env). If any other test fails, debug before proceeding.

- [ ] **Step 2: Smoke-test `resolve_models` end-to-end**

Run: `uv run python -c "from src.chain import resolve_models; models = resolve_models(); print(f'{len(models)} models resolved'); [print(f'  - {m.model_name if hasattr(m, \"model_name\") else m}') for m in models]"`

Expected: Prints a count and the model names. With at least one provider key set, should print ≥1 model.

- [ ] **Step 3: Dry-run the pipeline for an article URL**

Run: `uv run python -m src.main https://example.com/some-article --dry-run`
Expected: The pipeline runs end-to-end. The rendered Markdown should not include a title block injected from anywhere other than the model's structured output. The model prompt should include the source URL and source type.

- [ ] **Step 4: Verify the deps flow end-to-end with a real talk URL (only if LM Studio or a cloud provider is reachable)**

If reachable:

Run: `uv run python -m src.main https://www.youtube.com/watch?v=<some_id> --dry-run`
Expected: The rendered Markdown uses the yt-dlp title and channel verbatim. The `<meta>` block has the correct `source_url` and `source_type: talk`.

If not reachable, skip this step and note in the PR description that manual talk verification was not possible in this environment.

- [ ] **Step 5: Commit any final cleanup**

If anything was changed during verification (unlikely), commit. Otherwise, no commit needed.

---

## Summary of changes

| File | Net change |
|---|---|
| `src/providers.py` | -30 lines: deleted `ModelEntry` (-12), `resolve_provider` (-18); renamed semantics; same `PROVIDERS` registry. |
| `src/chain.py` | -80 lines: deleted `_lm_studio_entry` (-20), `resolve_full_chain` (-3), `resolve_cloud_chain` (-10), custom retry loop (-15). New: `setup` parameter, deps validation, `FallbackModel` wiring. |
| `src/agent.py` | +20 lines: added `_inject_talk_metadata` and `_setup_talk_metadata` module-level functions; `summarise()` now passes `setup` instead of string-injecting. |
| `tests/test_providers.py` | Renamed 1 class, 1 method; added `build_models` tests; updated 1 import. |
| `tests/test_chain.py` | Restructured: 1 class deleted, 1 renamed, 1 expanded. +8 new tests (3 for `resolve_models`, 5 for `call_with_fallback` including deps/validation, 1 for FunctionModel integration). |
| `tests/test_summariser.py` | 1 test rewritten + 2 new tests for non-talk and talk-without-deps paths. |

**Total: ~106 tests passing (up from 95).**

## Verification commands

- `uv run pytest tests/ -v` — full suite
- `uv run python -c "from src.chain import resolve_models; print(resolve_models())"` — smoke test
- `uv run python -m src.main <url> --dry-run` — end-to-end
