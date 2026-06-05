"""Application settings loaded from environment variables."""

from typing import Literal

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
    # VAULT_PATH is the in-container path the renderer writes to. The compose
    # file bind-mounts ./vault to /app/vault, so leave this alone in Docker.
    # Override only for local dev (e.g. VAULT_PATH=/home/you/some/folder).
    VAULT_FORMAT: Literal["obsidian", "logseq"] = "obsidian"
    VAULT_PATH: str = "/app/vault"


settings = Settings()
