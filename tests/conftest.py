import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def mock_lm_client():
    """Mock lm_client.ensure_model_loaded globally so tests don't need a real LM Studio."""
    with patch("src.agent.lm_client.ensure_model_loaded", new_callable=AsyncMock):
        yield
