"""Integration test: full pipeline with mocked providers."""

import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.main import run_pipeline
from src.models import ArticleNote, ContentType, VaultMetadata, Reflection


def _article_fixture():
    return ArticleNote(
        meta=VaultMetadata(
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
        with patch("src.vault.settings.VAULT_FORMAT", "obsidian"), \
             patch("src.vault.settings.VAULT_PATH", tmp), \
             patch("src.vault_index.settings.VAULT_FORMAT", "obsidian"), \
             patch("src.vault_index.settings.VAULT_PATH", tmp):
            with patch("src.main.fetch", new_callable=AsyncMock) as mock_fetch, \
                 patch("src.main.classify", new_callable=AsyncMock) as mock_classify, \
                 patch("src.main.summarise", new_callable=AsyncMock) as mock_summarise:
                mock_fetch.return_value = ("Article text here", None)
                mock_classify.return_value = ContentType.article
                mock_summarise.return_value = _article_fixture()

                path, note = await run_pipeline("https://example.com/article")

                assert path is not None
                assert path.exists()
                content = path.read_text()
                assert "Integration Article" in content
                assert "## Summary" in content
                mock_fetch.assert_called_once()
                mock_classify.assert_called_once()
                mock_summarise.assert_called_once()


@pytest.mark.asyncio
async def test_pipeline_dry_run_does_not_write():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("src.vault.settings.VAULT_FORMAT", "obsidian"), \
             patch("src.vault.settings.VAULT_PATH", tmp), \
             patch("src.vault_index.settings.VAULT_FORMAT", "obsidian"), \
             patch("src.vault_index.settings.VAULT_PATH", tmp):
            with patch("src.main.fetch", new_callable=AsyncMock) as mock_fetch, \
                 patch("src.main.classify", new_callable=AsyncMock) as mock_classify, \
                 patch("src.main.summarise", new_callable=AsyncMock) as mock_summarise:
                mock_fetch.return_value = ("Article text", None)
                mock_classify.return_value = ContentType.article
                mock_summarise.return_value = _article_fixture()

                path, note = await run_pipeline(
                    "https://example.com/article", dry_run=True
                )

                assert path is None
                inbox = Path(tmp) / "Inbox"
                assert not inbox.exists() or not any(inbox.iterdir())


@pytest.mark.asyncio
async def test_pipeline_dry_run_logseq_does_not_write():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("src.vault.settings.VAULT_FORMAT", "logseq"), \
             patch("src.vault.settings.VAULT_PATH", tmp), \
             patch("src.vault_index.settings.VAULT_FORMAT", "logseq"), \
             patch("src.vault_index.settings.VAULT_PATH", tmp):
            with patch("src.main.fetch", new_callable=AsyncMock) as mock_fetch, \
                 patch("src.main.classify", new_callable=AsyncMock) as mock_classify, \
                 patch("src.main.summarise", new_callable=AsyncMock) as mock_summarise:
                mock_fetch.return_value = ("Article text", None)
                mock_classify.return_value = ContentType.article
                mock_summarise.return_value = _article_fixture()

                path, note = await run_pipeline(
                    "https://example.com/article", dry_run=True
                )

                assert path is None
                pages = Path(tmp) / "pages"
                assert not pages.exists() or not any(pages.iterdir())
