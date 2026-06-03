"""Tests for the classifier (classify function)."""

from unittest.mock import AsyncMock, patch

import pytest

from src.agent import classify
from src.models import ContentType


@pytest.mark.asyncio
async def test_classify_returns_content_type_from_chain():
    """The classifier returns whatever the chain returns."""
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = ContentType.article
        result = await classify("Some article text about AI research")
        assert result == ContentType.article
        mock_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_classify_returns_talk_for_lecture_snippet():
    """Given talk-like text, classifier returns talk."""
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = ContentType.talk
        result = await classify("Welcome to my keynote on neural networks")
        assert result == ContentType.talk


@pytest.mark.asyncio
async def test_classify_returns_paper_for_academic_snippet():
    """Given paper-like text, classifier returns paper."""
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = ContentType.paper
        result = await classify("Abstract — We present a novel approach to...")
        assert result == ContentType.paper


@pytest.mark.asyncio
async def test_classify_returns_repo_for_github_readme():
    """Given repo-like text, classifier returns repo."""
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = ContentType.repo
        result = await classify("# awesome-lib\n\nA Python library for...")
        assert result == ContentType.repo


@pytest.mark.asyncio
async def test_classify_fallback_to_article_on_chain_exhausted():
    """If the chain returns None, default to ContentType.article."""
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = None
        result = await classify("Some random text")
        assert result == ContentType.article
