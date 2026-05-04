import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.models import ArticleNote, ContentType, ObsidianMetadata, Reflection
from src.main import run_pipeline


def _article_fixture():
    return ArticleNote(
        meta=ObsidianMetadata(
            tags=["integration-test"],
            source_url="https://example.com",
            source_type=ContentType.article,
            ingested_on=date(2026, 5, 4),
        ),
        title="Integration Article",
        author="Bot",
        thesis="It works",
        key_points=["P1"],
        evidence=["E1"],
        open_questions=[],
        reflection=Reflection(),
    )


@pytest.mark.asyncio
async def test_pipeline_full_run_writes_file():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("src.vault.settings.OBSIDIAN_VAULT_PATH", tmp):
            with patch("src.vault_index.settings.OBSIDIAN_VAULT_PATH", tmp):
                with patch("src.main.fetch", new_callable=AsyncMock) as mock_fetch:
                    mock_fetch.return_value = "Article text here"
                    with patch(
                        "src.main.summarise", new_callable=AsyncMock
                    ) as mock_summarise:
                        mock_summarise.return_value = _article_fixture()
                        path = await run_pipeline("https://example.com/article")
                        assert path is not None
                        assert path.exists()
                        content = path.read_text()
                        assert "Integration Article" in content
                        assert "## Summary" in content


@pytest.mark.asyncio
async def test_pipeline_dry_run_does_not_write():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("src.vault.settings.OBSIDIAN_VAULT_PATH", tmp):
            with patch("src.vault_index.settings.OBSIDIAN_VAULT_PATH", tmp):
                with patch("src.main.fetch", new_callable=AsyncMock) as mock_fetch:
                    mock_fetch.return_value = "Article text"
                    with patch(
                        "src.main.summarise", new_callable=AsyncMock
                    ) as mock_summarise:
                        mock_summarise.return_value = _article_fixture()
                        path = await run_pipeline(
                            "https://example.com/article", dry_run=True
                        )
                        assert path is None
                        inbox = Path(tmp) / "Inbox"
                        assert not inbox.exists() or not any(inbox.iterdir())
