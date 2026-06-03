import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel

from src.chain import call_with_fallback, resolve_cloud_chain, resolve_full_chain
from src.providers import ModelEntry
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
    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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
