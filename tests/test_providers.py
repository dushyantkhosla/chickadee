import os
import pytest
from unittest.mock import patch

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.vercel import VercelProvider

from src.providers import ProviderConfig, PROVIDERS, build_models


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
            models = build_models(config)
            assert models == []


class TestBuildModels:
    def test_yields_model_instances_for_valid_config(self):
        config = ProviderConfig(
            name="test",
            api_key_env="TEST_KEY",
            provider_type="openai",
            base_url="http://test.com",
            models_default="model-a,model-b",
        )
        with patch.dict(os.environ, {"TEST_KEY": "sk-test"}):
            models = build_models(config)
            assert len(models) == 2
            assert all(isinstance(m, OpenAIChatModel) for m in models)
            assert models[0].provider is models[1].provider

    def test_models_preserve_input_order_when_shuffle_false(self):
        config = ProviderConfig(
            name="test",
            api_key_env="TEST_KEY",
            provider_type="openai",
            base_url="http://test.com",
            models_default="model-a,model-b,model-c,model-d",
        )
        with patch.dict(os.environ, {"TEST_KEY": "sk-test"}):
            models = build_models(config, shuffle=False)
            names = [m.model_name for m in models]
            assert names == ["model-a", "model-b", "model-c", "model-d"]

    def test_models_can_be_shuffled_when_shuffle_true(self):
        """With shuffle=True, the function must not error and must return all models.
        We don't assert a specific order (shuffle is random) but we verify the contract
        is exercised and all models are returned.
        """
        config = ProviderConfig(
            name="test",
            api_key_env="TEST_KEY",
            provider_type="openai",
            base_url="http://test.com",
            models_default="model-a,model-b,model-c,model-d",
        )
        with patch.dict(os.environ, {"TEST_KEY": "sk-test"}):
            models = build_models(config, shuffle=True)
            names = {m.model_name for m in models}
            assert names == {"model-a", "model-b", "model-c", "model-d"}

    def test_vercel_provider_type(self):
        config = ProviderConfig(
            name="vercel",
            api_key_env="VERCEL_KEY",
            provider_type="vercel",
            models_default="openai/gpt-oss-20b",
        )
        with patch.dict(os.environ, {"VERCEL_KEY": "test-key"}):
            models = build_models(config)
            assert len(models) == 1
            assert isinstance(models[0], OpenAIChatModel)
            assert isinstance(models[0].provider, VercelProvider)
