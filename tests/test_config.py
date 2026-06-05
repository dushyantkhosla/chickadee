"""Tests for config module."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import Settings


def test_config_loads_from_env():
    s = Settings(
        VAULT_PATH="/custom/vault",
    )
    assert s.VAULT_PATH == "/custom/vault"


def test_config_loads_from_dotenv():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("VAULT_PATH=/dotenv/vault\n")
        f.flush()
        path = f.name

    try:
        s = Settings(_env_file=path)
        assert s.VAULT_PATH == "/dotenv/vault"
    finally:
        os.unlink(path)


def test_config_vault_backend_default():
    with patch.dict(os.environ, {}, clear=True):
        s = Settings(_env_file=None)
        assert s.VAULT_FORMAT == "obsidian"


def test_config_vault_backend_logseq():
    with patch.dict(os.environ, {"VAULT_FORMAT": "logseq"}, clear=False):
        s = Settings(_env_file=None)
        assert s.VAULT_FORMAT == "logseq"


def test_config_vault_backend_invalid():
    with patch.dict(os.environ, {"VAULT_FORMAT": "notavalid"}, clear=False):
        with pytest.raises(Exception):  # ValidationError
            Settings(_env_file=None)


def test_lm_studio_defaults():
    """When no .env is present, LM Studio settings have sensible defaults."""
    with patch.dict(os.environ, {}, clear=True):
        s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.LM_STUDIO_BASE_URL == "http://localhost:1234/v1"
    assert s.LM_STUDIO_MODEL == "gemma-4-e4b-it"


def test_lm_studio_from_env():
    """LM Studio settings are overridable via environment / .env."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("LM_STUDIO_BASE_URL=http://192.168.1.50:1234/v1\n")
        f.write("LM_STUDIO_MODEL=qwen2.5-7b\n")
        f.flush()
        path = f.name
    try:
        with patch.dict(os.environ, {}, clear=True):
            s = Settings(_env_file=path)  # type: ignore[call-arg]
        assert s.LM_STUDIO_BASE_URL == "http://192.168.1.50:1234/v1"
        assert s.LM_STUDIO_MODEL == "qwen2.5-7b"
    finally:
        Path(path).unlink()


def test_default_lm_studio_model():
    with patch.dict(os.environ, {}, clear=True):
        s = Settings(_env_file=None)
        assert s.LM_STUDIO_MODEL == "gemma-4-e4b-it"


def test_paid_fallback_default():
    """Final-fallback model list is set to a non-empty default."""
    with patch.dict(os.environ, {}, clear=True):
        s = Settings(_env_file=None)
    assert "deepseek/deepseek-v3.2" in s.OPENROUTER_PAID_MODELS


def test_no_anthropic_key():
    with patch.dict(os.environ, {}, clear=True):
        s = Settings(_env_file=None)
        assert not hasattr(s, "ANTHROPIC_API_KEY") or s.ANTHROPIC_API_KEY == ""


def test_free_pool_defaults():
    with patch.dict(os.environ, {}, clear=True):
        s = Settings(_env_file=None)
        assert "gemma4:31b" in s.OLLAMA_MODELS
        assert "mistral-small-latest" in s.MISTRAL_MODELS
        assert "gemini-2.5-flash" in s.GOOGLE_MODELS
        assert "google/gemma-4-26b-a4b-it:free" in s.OPENROUTER_FREE_MODELS
