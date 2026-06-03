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
