"""Application settings loaded from environment / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ANTHROPIC_API_KEY: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    BOT_ALLOWED_CHAT_IDS: str = "*"

    LM_STUDIO_BASE_URL: str = "http://localhost:1234/v1"
    LM_STUDIO_MODEL: str = "local-model"
    LM_STUDIO_API_KEY: str = ""

    # Vault mode — choose one
    OBSIDIAN_VAULT_PATH: str = "/tmp/chickadee-vault"
    OBSIDIAN_API_KEY: str = ""
    OBSIDIAN_BASE_URL: str = ""


settings = Settings()
