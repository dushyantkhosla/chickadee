"""Tests for Logseq property rendering."""
from datetime import date
from unittest.mock import patch

from src.models import (
    ArticleNote,
    ContentType,
    VaultMetadata,
    Reflection,
    TalkNote,
)
from src.renderer import render


def _meta(**kwargs):
    defaults = dict(
        tags=["machine-learning"],
        source_url="https://example.com/article",
        source_type=ContentType.article,
        ingested_on=date(2026, 5, 4),
    )
    defaults.update(kwargs)
    return VaultMetadata(**defaults)


def test_logseq_properties_format():
    note = ArticleNote(
        meta=_meta(
            builds_on=["Prior Work"],
            see_also=["Related"],
        ),
        title="Test Article",
        author="Alice",
        thesis="Testing is good",
        key_points=["Point A"],
        evidence=["Study X"],
        open_questions=[],
        reflection=Reflection(),
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "logseq"
        md = render(note)
    assert md.startswith("tags:: machine-learning")
    assert "builds-on:: [[Prior Work]]" in md
    assert "see-also:: [[Related]]" in md
    assert "source-url:: https://example.com/article" in md
    assert "source-type:: article" in md
    assert "ingested-on:: 2026-05-04" in md
    assert "---" not in md  # No YAML frontmatter


def test_logseq_omits_empty_properties():
    note = ArticleNote(
        meta=_meta(),
        title="Sparse",
        author="Bob",
        thesis="Sparse",
        key_points=[],
        evidence=[],
        open_questions=[],
        reflection=Reflection(),
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "logseq"
        md = render(note)
    assert "builds-on::" not in md
    assert "see-also::" not in md
    assert "contradicts::" not in md


def test_logseq_upload_date_property():
    note = ArticleNote(
        meta=_meta(upload_date=date(2026, 3, 15)),
        title="Dated Article",
        thesis="Has upload date",
        key_points=[],
        evidence=[],
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "logseq"
        md = render(note)
    assert "upload-date:: 2026-03-15" in md


def test_logseq_body_unchanged():
    note = TalkNote(
        meta=_meta(source_type=ContentType.talk),
        title="A Talk",
        speaker="Alice",
        thesis="Talk thesis",
        arguments=["Arg 1"],
        key_quotes=["Quote 1"],
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "logseq"
        md = render(note)
    assert "# A Talk" in md
    assert "## Summary" in md
    assert "## Arguments" in md
    assert "> Quote 1" in md


def test_logseq_contradicts_property():
    note = ArticleNote(
        meta=_meta(contradicts=["Flawed Study"]),
        title="Refutation",
        thesis="Opposing view",
        key_points=[],
        evidence=[],
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "logseq"
        md = render(note)
    assert "contradicts:: [[Flawed Study]]" in md


def test_logseq_multiple_tags():
    note = ArticleNote(
        meta=_meta(tags=["ml", "python", "research"]),
        title="Multi-tag",
        thesis="Tags test",
        key_points=[],
        evidence=[],
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "logseq"
        md = render(note)
    assert "tags:: ml, python, research" in md


def test_logseq_multiple_builds_on():
    note = ArticleNote(
        meta=_meta(builds_on=["Note A", "Note B"]),
        title="Multi-link",
        thesis="Links test",
        key_points=[],
        evidence=[],
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "logseq"
        md = render(note)
    assert "builds-on:: [[Note A]], [[Note B]]" in md


def test_render_obsidian_backend_produces_yaml_frontmatter():
    note = ArticleNote(
        meta=_meta(),
        title="Obsidian Backend",
        thesis="YAML frontmatter test",
        key_points=[],
        evidence=[],
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "obsidian"
        md = render(note)
    assert md.startswith("---")
