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
