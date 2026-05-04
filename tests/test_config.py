import os
import tempfile
from pathlib import Path

from src.config import Settings


def test_config_loads_from_env():
    s = Settings(
        ANTHROPIC_API_KEY="test-key",
        OBSIDIAN_VAULT_PATH="/custom/vault",
    )
    assert s.ANTHROPIC_API_KEY == "test-key"
    assert s.OBSIDIAN_VAULT_PATH == "/custom/vault"


def test_config_loads_from_dotenv():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("ANTHROPIC_API_KEY=dotenv-key\n")
        f.write("OBSIDIAN_VAULT_PATH=/dotenv/vault\n")
        f.flush()
        path = f.name

    try:
        # Pydantic-settings requires env_file to be passed explicitly
        # when not at cwd; we verify the mechanism works.
        s = Settings(_env_file=path)
        assert s.ANTHROPIC_API_KEY == "dotenv-key"
        assert s.OBSIDIAN_VAULT_PATH == "/dotenv/vault"
    finally:
        os.unlink(path)


def test_lm_studio_defaults():
    """When no .env is present, LM Studio settings have sensible defaults."""
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.LM_STUDIO_BASE_URL == "http://localhost:1234/v1"
    assert s.LM_STUDIO_MODEL == "local-model"


def test_lm_studio_from_env():
    """LM Studio settings are overridable via environment / .env."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("LM_STUDIO_BASE_URL=http://192.168.1.50:1234/v1\n")
        f.write("LM_STUDIO_MODEL=qwen2.5-7b\n")
        f.flush()
        s = Settings(_env_file=f.name)  # type: ignore[call-arg]
        assert s.LM_STUDIO_BASE_URL == "http://192.168.1.50:1234/v1"
        assert s.LM_STUDIO_MODEL == "qwen2.5-7b"
    Path(f.name).unlink()
