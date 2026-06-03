import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel

from src.chain import call_with_fallback, resolve_models
from src.providers import build_models
from src.agent import TalkMetadata
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


class DummyOutput(BaseModel):
    value: str


class TestResolveModels:
    def test_includes_lm_studio_when_reachable(self):
        sentinel = OpenAIChatModel("gemma-4-e4b-it", provider=OpenAIProvider(base_url="http://test", api_key="x"))
        with patch("src.chain._lm_studio_reachable", return_value=True), \
             patch("src.chain._build_lm_studio_model", return_value=sentinel), \
             patch("src.chain.build_models", return_value=[]):
            models = resolve_models()
            assert models[0] is sentinel

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
             patch("src.chain.FallbackModel") as MockFallback, \
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
             patch("src.chain.FallbackModel"), \
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
             patch("src.chain.FallbackModel"), \
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
             patch("src.chain.FallbackModel"), \
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
             patch("src.chain.FallbackModel"), \
             patch("src.chain.Agent") as MockAgent:
            MockAgent.return_value.run = AsyncMock(
                return_value=MagicMock(output=DummyOutput(value="ok"))
            )
            await call_with_fallback("sp", "up", DummyOutput, setup=my_setup)
            assert setup_called == [MockAgent.return_value]


from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart


class TestSetupCallbackAttachesInstructions:
    @pytest.mark.asyncio
    async def test_metadata_reaches_system_instructions_via_setup(self):
        from pydantic_ai import Agent, RunContext

        captured_info = []

        def fn_model(messages: list[ModelMessage], info) -> ModelResponse:
            captured_info.append(info)
            return ModelResponse(parts=[TextPart('{"value": "ok"}')])

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

        # Build a real Agent in the test so we can verify instructions land
        # in info.instructions via FunctionModel.
        agent = Agent(
            model=FunctionModel(fn_model),
            deps_type=TalkMetadata,
            output_type=DummyOutput,
            instructions="Static instructions",
        )
        setup(agent)
        await agent.run("transcript", deps=deps)

        assert len(captured_info) == 1
        combined = captured_info[0].instructions
        assert "The Talk Title" in combined
        assert "Dr. Speaker" in combined
        assert "Static instructions" in combined
