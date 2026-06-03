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
