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
from typing import Type, TypeVar

import httpx
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from src.providers import (
    PROVIDERS,
    ModelEntry,
    resolve_provider,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _lm_studio_entry() -> ModelEntry | None:
    """Build a ModelEntry for LM Studio if reachable. Returns None otherwise."""
    base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
    model_name = os.getenv("LM_STUDIO_MODEL", "gemma-4-e4b-it")
    api_key = os.getenv("LM_STUDIO_API_KEY", "")

    # Sync probe — fast check with short timeout
    try:
        with httpx.Client(timeout=3.0) as probe:
            resp = probe.get(f"{base_url.rstrip('/')}/models")
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
