from datetime import date

import pytest
import yaml

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
from src.renderer import render


def _meta(**kwargs):
    defaults = dict(
        tags=["machine-learning"],
        source_url="https://example.com/article",
        source_type=ContentType.article,
        ingested_on=date(2026, 5, 4),
    )
    defaults.update(kwargs)
    return ObsidianMetadata(**defaults)


def _parse_frontmatter(md: str) -> dict:
    assert md.startswith("---")
    parts = md.split("---", 2)
    return yaml.safe_load(parts[1])


def test_render_article_note():
    note = ArticleNote(
        meta=_meta(
            source_type=ContentType.article,
            builds_on=["Prior Work"],
            see_also=["Related"],
            contradicts=[],
        ),
        title="Test Article",
        author="Alice",
        thesis="Testing is good",
        key_points=["Point A", "Point B"],
        evidence=["Study X"],
        open_questions=["Q1"],
        reflection=Reflection(my_take="Nice", so_what="Important", now_what="Do it"),
    )
    md = render(note)
    fm = _parse_frontmatter(md)
    assert fm["tags"] == ["machine-learning"]
    assert any("Prior Work" in item for item in fm["builds_on"])
    assert fm["source_type"] == "article"
    assert "# Test Article" in md
    assert "## Summary" in md
    assert "Testing is good" in md
    assert "## Key points" in md
    assert "- Point A" in md
    assert "## Evidence" in md
    assert "## Open questions" in md
    assert "- Q1" in md
    assert "## Reflection" in md
    assert "**My take:** Nice" in md
    assert "**So what:** Important" in md
    assert "**Now what:** Do it" in md


def test_render_omits_empty_open_questions():
    note = ArticleNote(
        meta=_meta(),
        title="No Questions",
        author="Bob",
        thesis="Nothing",
        key_points=[],
        evidence=[],
        open_questions=[],
        reflection=Reflection(),
    )
    md = render(note)
    assert "## Open questions" not in md


def test_render_omits_none_reflection_fields():
    note = ArticleNote(
        meta=_meta(),
        title="Sparse",
        author="Bob",
        thesis="Sparse",
        key_points=[],
        evidence=[],
        open_questions=[],
        reflection=Reflection(my_take="Only this"),
    )
    md = render(note)
    assert "**My take:** Only this" in md
    assert "**So what:**" not in md
    assert "**Now what:**" not in md


def test_render_talk_note_with_venue_and_quotes():
    note = TalkNote(
        meta=_meta(source_type=ContentType.talk),
        title="A Talk",
        speaker="Alice",
        venue="PyCon",
        thesis="Talk thesis",
        arguments=["Arg 1"],
        key_quotes=["Quote 1"],
        open_questions=[],
        reflection=Reflection(),
    )
    md = render(note)
    assert "_Alice — PyCon_" in md
    assert "## Key quotes" in md
    assert "> Quote 1" in md


def test_render_paper_note():
    note = PaperNote(
        meta=_meta(source_type=ContentType.paper),
        title="A Paper",
        authors=["Alice", "Bob"],
        year=2025,
        hypothesis="H1",
        methodology="Simulations",
        findings=["F1"],
        limitations=["Small sample"],
        open_questions=[],
        reflection=Reflection(),
    )
    md = render(note)
    assert "_Alice, Bob (2025)_" in md
    assert "## Methodology" in md
    assert "## Findings" in md
    assert "## Limitations" in md
    assert "- Small sample" in md


def test_render_essay_note():
    note = EssayNote(
        meta=_meta(source_type=ContentType.essay),
        title="An Essay",
        author="Dave",
        thesis="Opinion",
        claimed=["C1"],
        evidenced=["E1"],
        open_questions=[],
        reflection=Reflection(),
    )
    md = render(note)
    assert "## Claimed (unverified)" in md
    assert "## Evidenced" in md


def test_render_repo_note():
    note = RepoNote(
        meta=_meta(source_type=ContentType.repo),
        name="awesome-repo",
        what_it_does="Does things",
        stack=["Python", "Rust"],
        key_patterns=["Factory"],
        open_questions=[],
        reflection=Reflection(),
    )
    md = render(note)
    assert "# awesome-repo" in md
    assert "## Stack" in md
    assert "- Python" in md


def test_render_field_note_special_sections():
    note = FieldNote(
        meta=_meta(source_type=ContentType.field),
        title="Field Report",
        author="Charlie",
        subject="Tool X",
        what_changed="Got faster",
        data_points=["2x speedup"],
        code_snippets=["pip install x"],
        authors_take="Promising",
        shelf_life=ShelfLife.months,
        open_questions=[],
        reflection=Reflection(),
    )
    md = render(note)
    assert "## Data points" in md
    assert "## Code" in md
    assert "```bash" in md
    assert "pip install x" in md
    assert "**Author's take:** Promising" in md
    assert "**Shelf life:** months" in md
