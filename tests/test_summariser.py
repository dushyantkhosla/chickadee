from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent import summarise
from src.models import (
    ArticleNote,
    ContentType,
    EssayNote,
    FieldNote,
    ObsidianMetadata,
    PaperNote,
    Reflection,
    RepoNote,
    ShelfLife,
    TalkNote,
)


def _meta(source_type: ContentType):
    return ObsidianMetadata(
        tags=["test"],
        source_url="https://example.com",
        source_type=source_type,
        ingested_on=date(2026, 5, 4),
    )


@pytest.mark.asyncio
async def test_summarise_returns_talk_note():
    note = TalkNote(
        meta=_meta(ContentType.talk),
        title="A Talk",
        speaker="Alice",
        thesis="AI changes things",
        arguments=["Point 1"],
        key_quotes=["Quote 1"],
        open_questions=[],
        reflection=Reflection(my_take=None, so_what=None, now_what=None),
    )
    with patch("src.agent.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=MagicMock(output=note))
        MockAgent.return_value = mock_instance

        result = await summarise("text", ContentType.talk, [], "https://example.com")
        assert isinstance(result, TalkNote)
        assert result.title == "A Talk"
        assert result.reflection.my_take is None


@pytest.mark.asyncio
async def test_summarise_returns_article_note():
    note = ArticleNote(
        meta=_meta(ContentType.article),
        title="An Article",
        author="Bob",
        thesis="A point",
        key_points=["P1"],
        evidence=["E1"],
        open_questions=["Q1"],
        reflection=Reflection(my_take="Nice", so_what=None, now_what=None),
    )
    with patch("src.agent.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=MagicMock(output=note))
        MockAgent.return_value = mock_instance

        result = await summarise("text", ContentType.article, [], "https://example.com")
        assert isinstance(result, ArticleNote)
        assert result.reflection.so_what is None


@pytest.mark.asyncio
async def test_summarise_returns_paper_note():
    note = PaperNote(
        meta=_meta(ContentType.paper),
        title="A Paper",
        authors=["Carol"],
        year=2025,
        hypothesis="H1",
        methodology="Sim",
        findings=["F1"],
        limitations=["L1"],
        open_questions=[],
        reflection=Reflection(),
    )
    with patch("src.agent.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=MagicMock(output=note))
        MockAgent.return_value = mock_instance

        result = await summarise("text", ContentType.paper, [], "https://example.com")
        assert isinstance(result, PaperNote)


@pytest.mark.asyncio
async def test_summarise_returns_essay_note():
    note = EssayNote(
        meta=_meta(ContentType.essay),
        title="An Essay",
        author="Dave",
        thesis="Opinion",
        claimed=["C1"],
        evidenced=["E1"],
        open_questions=[],
        reflection=Reflection(),
    )
    with patch("src.agent.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=MagicMock(output=note))
        MockAgent.return_value = mock_instance

        result = await summarise("text", ContentType.essay, [], "https://example.com")
        assert isinstance(result, EssayNote)


@pytest.mark.asyncio
async def test_summarise_returns_repo_note():
    note = RepoNote(
        meta=_meta(ContentType.repo),
        name="repo",
        what_it_does="Does things",
        stack=["python"],
        key_patterns=["pattern"],
        open_questions=[],
        reflection=Reflection(),
    )
    with patch("src.agent.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=MagicMock(output=note))
        MockAgent.return_value = mock_instance

        result = await summarise("text", ContentType.repo, [], "https://example.com")
        assert isinstance(result, RepoNote)


@pytest.mark.asyncio
async def test_summarise_returns_field_note():
    note = FieldNote(
        meta=_meta(ContentType.field),
        title="Field Report",
        author="Eve",
        subject="Tool X",
        what_changed="Faster",
        data_points=["2x"],
        code_snippets=["pip install x"],
        authors_take="Good",
        shelf_life=ShelfLife.months,
        open_questions=[],
        reflection=Reflection(),
    )
    with patch("src.agent.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=MagicMock(output=note))
        MockAgent.return_value = mock_instance

        result = await summarise("text", ContentType.field, [], "https://example.com")
        assert isinstance(result, FieldNote)


@pytest.mark.asyncio
async def test_summarise_prompt_includes_vault_titles():
    vault_titles = ["Existing Note", "Another Note"]
    with patch("src.agent.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=MagicMock(output=MagicMock()))
        MockAgent.return_value = mock_instance

        await summarise("text", ContentType.article, vault_titles, "https://example.com")

        call_kwargs = MockAgent.call_args.kwargs
        assert "Existing Note" in call_kwargs["instructions"]
        assert "Another Note" in call_kwargs["instructions"]
        assert call_kwargs["output_type"] == ArticleNote


@pytest.mark.asyncio
async def test_summarise_prompt_includes_url_and_type():
    with patch("src.agent.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=MagicMock(output=MagicMock()))
        MockAgent.return_value = mock_instance

        await summarise("text", ContentType.talk, [], "https://talk.example.com")

        call_kwargs = MockAgent.call_args.kwargs
        assert "https://talk.example.com" in call_kwargs["instructions"]
        assert ContentType.talk.value in call_kwargs["instructions"]
