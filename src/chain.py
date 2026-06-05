"""LLM provider chain — resolves models and runs via PydanticAI FallbackModel.

Priority order:
1. LM Studio (laptop, when reachable) — free
2. Free cloud pool: Google direct, Mistral direct, Ollama, OpenRouter free
3. OpenRouter paid (deepseek/deepseek-chat) — final fallback when all free fails

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

_CLOUD_PROVIDER_ORDER = ["google:free", "mistral:free", "ollama", "openrouter:free", "openrouter:paid"]


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
