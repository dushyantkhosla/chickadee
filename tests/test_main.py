from unittest.mock import AsyncMock, patch

import pytest

from src.models import ContentType


@pytest.mark.asyncio
async def test_main_flow_router_hit_no_classifier():
    """Unambiguous domain → router returns type, classifier never called."""
    from src.main import resolve_content_type

    with patch("src.main.classify", new_callable=AsyncMock) as mock_classify:
        result = await resolve_content_type("https://youtube.com/watch?v=abc")
        assert result == ContentType.talk
        mock_classify.assert_not_awaited()


@pytest.mark.asyncio
async def test_main_flow_router_miss_calls_classifier():
    """Ambiguous domain → router returns None, classifier is called."""
    from src.main import resolve_content_type

    with patch("src.main.classify", new_callable=AsyncMock) as mock_classify:
        mock_classify.return_value = ContentType.article
        result = await resolve_content_type("https://example.com/blog/post")
        assert result == ContentType.article
        mock_classify.assert_awaited_once()
