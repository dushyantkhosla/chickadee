"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="",
        extra="ignore",
    )

    # ── Telegram ──────────────────────────────────────────────────────────
    CHICKADEE_TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    CHICKADEE_ALLOWED_CHAT_IDS: str = "*"

    # ── LM Studio (laptop, primary when available) ───────────────────────
    LM_STUDIO_BASE_URL: str = "http://localhost:1234/v1"
    LM_STUDIO_MODEL: str = "gemma-4-e4b-it"
    LM_STUDIO_API_KEY: str = ""

    # ── Free pool providers ──────────────────────────────────────────────
    # Model lists are the source of truth in docker-compose.yml. These
    # defaults are used when running outside the container (local dev, probe).
    OLLAMA_API_KEY: str = ""
    OLLAMA_MODELS: str = "gemma4:31b"

    MISTRAL_API_KEY: str = ""
    MISTRAL_MODELS: str = "mistral-small-latest"

    GOOGLE_API_KEY: str = ""
    GOOGLE_MODELS: str = "gemini-2.5-flash"

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_FREE_MODELS: str = "google/gemma-4-26b-a4b-it:free,google/gemma-4-31b-it:free"

    # ── OpenRouter paid (final fallback) ────────────────────────────────
    OPENROUTER_PAID_MODELS: str = "openai/gpt-5-nano,deepseek/deepseek-v3.2,openai/gpt-4o-mini"

    # ── Transcription (YouTube audio → text via OpenRouter) ─────────────
    TRANSCRIPTION_MODEL: str = "xiaomi/mimo-v2.5"

    # ── Vault ────────────────────────────────────────────────────────────
    # VAULT_PATH is the in-container path the renderer writes to. The compose
    # file bind-mounts ./vault to /app/vault, so leave this alone in Docker.
    # Override only for local dev (e.g. VAULT_PATH=/home/you/some/folder).
    VAULT_PATH: str = "/app/vault"


settings = Settings()
