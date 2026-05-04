"""Tests for Telegram bot — formatting and config."""

import pytest
from src.config import settings
from src.bot import format_confirmation, format_error


def test_config_has_bot_fields():
    """Config loads telegram-related env vars."""
    # These should exist without crashing
    assert hasattr(settings, "TELEGRAM_BOT_TOKEN")
    assert hasattr(settings, "BOT_ALLOWED_CHAT_IDS")


def test_format_confirmation_article():
    """ArticleNote produces a formatted confirmation message."""
    from datetime import date
    from src.models import ArticleNote, ObsidianMetadata, ContentType

    note = ArticleNote(
        meta=ObsidianMetadata(
            tags=["python", "testing"],
            source_url="https://example.com/article",
            source_type=ContentType.article,
            ingested_on=date.today(),
        ),
        title="Test Article",
        thesis="This is a test article about testing things thoroughly.",
        key_points=["Point one"],
        evidence=["Evidence one"],
    )
    msg = format_confirmation(note, "2026-05-04_test-article.md")
    assert "✅" in msg
    assert "Test Article" in msg
    assert "python" in msg
    assert "testing things thoroughly" in msg
    assert "test-article.md" in msg


def test_format_confirmation_repo():
    """RepoNote uses 'name' instead of 'title'."""
    from datetime import date
    from src.models import RepoNote, ObsidianMetadata, ContentType

    note = RepoNote(
        meta=ObsidianMetadata(
            tags=["tooling"],
            source_url="https://github.com/example/repo",
            source_type=ContentType.repo,
            ingested_on=date.today(),
        ),
        name="chickadee",
        what_it_does="A summarisation pipeline",
        stack=["Python"],
        key_patterns=["Agent pattern"],
    )
    msg = format_confirmation(note, "2026-05-04_chickadee.md")
    assert "chickadee" in msg
    assert "tooling" in msg


def test_format_error():
    """Error message includes error type and URL."""
    msg = format_error("FetchError", "Could not fetch", "https://example.com")
    assert "FetchError" in msg
    assert "Could not fetch" in msg
    assert "https://example.com" in msg
