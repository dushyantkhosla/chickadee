import os
import pytest
from unittest.mock import patch

from src.providers import ModelEntry, ProviderConfig, PROVIDERS, resolve_provider


class TestProviderConfig:
    def test_get_models_from_env(self):
        config = ProviderConfig(
            name="test",
            api_key_env="TEST_KEY",
            provider_type="openai",
            base_url="http://test.com",
            models_env="TEST_MODELS",
            models_default="model-a,model-b",
        )
        with patch.dict(os.environ, {"TEST_MODELS": "model-x,model-y"}):
            assert config.get_models() == ["model-x", "model-y"]

    def test_get_models_from_default(self):
        config = ProviderConfig(
            name="test",
            api_key_env="TEST_KEY",
            provider_type="openai",
            base_url="http://test.com",
            models_env="TEST_MODELS",
            models_default="model-a,model-b",
        )
        with patch.dict(os.environ, {}, clear=True):
            assert config.get_models() == ["model-a", "model-b"]

    def test_returns_empty_when_no_key(self):
        config = ProviderConfig(
            name="test",
            api_key_env="MISSING_KEY",
            provider_type="openai",
            base_url="http://test.com",
            models_default="model-a",
        )
        with patch.dict(os.environ, {}, clear=True):
            entries = list(resolve_provider(config))
            assert entries == []


class TestResolveProvider:
    def test_yields_model_entries_for_valid_config(self):
        config = ProviderConfig(
            name="test",
            api_key_env="TEST_KEY",
            provider_type="openai",
            base_url="http://test.com",
            models_default="model-a,model-b",
        )
        with patch.dict(os.environ, {"TEST_KEY": "sk-test"}):
            entries = list(resolve_provider(config))
            assert len(entries) == 2
            assert all(isinstance(e, ModelEntry) for e in entries)
            assert entries[0].label.startswith("test:")
            assert entries[1].label.startswith("test:")

    def test_vercel_provider_type(self):
        config = ProviderConfig(
            name="vercel",
            api_key_env="VERCEL_KEY",
            provider_type="vercel",
            models_default="openai/gpt-oss-20b",
        )
        with patch.dict(os.environ, {"VERCEL_KEY": "test-key"}):
            entries = list(resolve_provider(config))
            assert len(entries) == 1
