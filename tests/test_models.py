from datetime import date

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
    note_to_slug,
)


def _meta():
    return ObsidianMetadata(
        tags=["test"],
        source_url="https://example.com",
        source_type=ContentType.article,
        ingested_on=date.today(),
    )


def _reflection():
    return Reflection(my_take="Interesting", so_what="It matters", now_what="Read more")


def test_talk_note():
    note = TalkNote(
        meta=_meta(),
        title="A Talk",
        speaker="Alice",
        thesis="Something important",
        arguments=["Point 1"],
        key_quotes=["Quote 1"],
        open_questions=["Q1"],
        reflection=_reflection(),
    )
    d = note.model_dump()
    assert d["title"] == "A Talk"
    assert d["speaker"] == "Alice"


def test_article_note():
    note = ArticleNote(
        meta=_meta(),
        title="An Article",
        author="Bob",
        thesis="A point",
        key_points=["P1"],
        evidence=["E1"],
        open_questions=["Q1"],
        reflection=_reflection(),
    )
    assert note.model_dump()["title"] == "An Article"


def test_paper_note():
    note = PaperNote(
        meta=_meta(),
        title="A Paper",
        authors=["Carol"],
        year=2025,
        hypothesis="H1",
        methodology="Method",
        findings=["F1"],
        limitations=["L1"],
        open_questions=["Q1"],
        reflection=_reflection(),
    )
    assert note.model_dump()["year"] == 2025


def test_essay_note():
    note = EssayNote(
        meta=_meta(),
        title="An Essay",
        author="Dave",
        thesis="An opinion",
        claimed=["C1"],
        evidenced=["E1"],
        open_questions=["Q1"],
        reflection=_reflection(),
    )
    assert note.model_dump()["claimed"] == ["C1"]


def test_repo_note():
    note = RepoNote(
        meta=_meta(),
        name="repo",
        what_it_does="Does things",
        stack=["python"],
        key_patterns=["pattern"],
        open_questions=["Q1"],
        reflection=_reflection(),
    )
    assert note.model_dump()["name"] == "repo"


def test_field_note():
    note = FieldNote(
        meta=_meta(),
        title="A Field Note",
        author="Eve",
        subject="Tool X",
        what_changed="It got faster",
        data_points=["2x speedup"],
        code_snippets=["code"],
        authors_take="Great tool",
        shelf_life=ShelfLife.months,
        open_questions=["Q1"],
        reflection=_reflection(),
    )
    assert note.model_dump()["shelf_life"] == "months"


def test_note_to_slug_truncates_long_title():
    note = ArticleNote(
        meta=_meta(),
        title="This Is a Very Long Article Title That Would Make a Ridiculously Long Filename Because It Keeps Going and Going",
        author="Bot",
        thesis="Short",
        key_points=[],
        evidence=[],
        open_questions=[],
    )
    slug = note_to_slug(note)
    assert len(slug) <= 50
    assert not slug.endswith("-")


def test_note_to_slug_uses_name_for_repo():
    note = RepoNote(
        meta=_meta(),
        name="My Awesome Repo",
        what_it_does="Does cool stuff",
        stack=[],
        key_patterns=[],
    )
    assert note_to_slug(note) == "my-awesome-repo"
