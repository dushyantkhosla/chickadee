"""Tests for the summariser (summarise function)."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent import summarise, TalkMetadata
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
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = note
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
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = note
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
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = note
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
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = note
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
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = note
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
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = note
        result = await summarise("text", ContentType.field, [], "https://example.com")
        assert isinstance(result, FieldNote)


@pytest.mark.asyncio
async def test_summarise_prompt_includes_vault_titles():
    vault_titles = ["Existing Note", "Another Note"]
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = MagicMock()
        await summarise("text", ContentType.article, vault_titles, "https://example.com")

        call_kwargs = mock_call.call_args.kwargs
        assert "Existing Note" in call_kwargs["system_prompt"]
        assert "Another Note" in call_kwargs["system_prompt"]
        assert call_kwargs["output_type"] == ArticleNote


@pytest.mark.asyncio
async def test_summarise_prompt_includes_url_and_type():
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = MagicMock()
        await summarise("text", ContentType.talk, [], "https://talk.example.com")

        call_kwargs = mock_call.call_args.kwargs
        assert "https://talk.example.com" in call_kwargs["system_prompt"]
        assert ContentType.talk.value in call_kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_summarise_raises_when_chain_exhausted():
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = None
        with pytest.raises(RuntimeError, match="all providers exhausted"):
            await summarise("text", ContentType.article, [], "https://example.com")


@pytest.mark.asyncio
async def test_summarise_talk_with_deps_injects_metadata():
    """When TalkMetadata is provided, it should be injected into the user prompt."""
    note = MagicMock()
    deps = TalkMetadata(
        title="Test Talk",
        speaker="Test Speaker",
        categories=["ai", "ml"],
        upload_date=date(2026, 1, 1),
    )
    with patch("src.agent.call_with_fallback", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = note
        result = await summarise(
            "Transcript text",
            ContentType.talk,
            [],
            "https://youtube.com/watch?v=123",
            deps=deps,
        )
        assert result == note
        call_kwargs = mock_call.call_args.kwargs
        user_prompt = call_kwargs["user_prompt"]
        assert "Test Talk" in user_prompt
        assert "Test Speaker" in user_prompt
        assert "ai, ml" in user_prompt
        assert "2026-01-01" in user_prompt
