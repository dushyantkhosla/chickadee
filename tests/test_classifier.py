from unittest.mock import AsyncMock, patch

import pytest

from pydantic_ai.models.test import TestModel

from src.agent import _classifier_agent, classify
from src.models import ContentType


@pytest.mark.asyncio
async def test_classify_returns_content_type():
    """The classifier returns a valid ContentType enum member."""
    with _classifier_agent.override(model=TestModel()):
        result = await classify("Some article text about AI research")
        assert isinstance(result, ContentType)


@pytest.mark.asyncio
async def test_classify_returns_talk_for_lecture_snippet():
    """Given talk-like text, classifier returns talk."""
    with patch.object(_classifier_agent, "run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value.output = ContentType.talk
        result = await classify("Welcome to my keynote on neural networks")
        assert result == ContentType.talk
        mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_classify_returns_paper_for_academic_snippet():
    """Given paper-like text, classifier returns paper."""
    with patch.object(_classifier_agent, "run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value.output = ContentType.paper
        result = await classify("Abstract — We present a novel approach to...")
        assert result == ContentType.paper


@pytest.mark.asyncio
async def test_classify_returns_repo_for_github_readme():
    """Given repo-like text, classifier returns repo."""
    with patch.object(_classifier_agent, "run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value.output = ContentType.repo
        result = await classify("# awesome-lib\n\nA Python library for...")
        assert result == ContentType.repo


@pytest.mark.asyncio
async def test_classify_fallback_to_article_on_agent_error():
    """If the LLM call fails, default to ContentType.article."""
    with patch.object(_classifier_agent, "run", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = RuntimeError("LM Studio unreachable")
        result = await classify("Some random text")
        assert result == ContentType.article
