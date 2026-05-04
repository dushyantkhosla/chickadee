"""
Structured summarisation pipeline — Pydantic models
====================================================
Each *Note type maps to a content category detected via two-tier routing:
(1) UNAMBIGUOUS_DOMAINS — URL alone determines type, no LLM needed.
(2) Everything else — LLM classifies from article text before summarising.
All notes embed ObsidianMetadata (vault housekeeping) and Reflection
(personal interpretation).

Content types
-------------
TalkNote    — YouTube talks, conference presentations, podcasts
ArticleNote — Blog posts, journalism, general web articles
PaperNote   — Academic papers (arXiv, DOI, journal links)
EssayNote   — Opinion / long-form writing (Substack, personal sites)
RepoNote    — GitHub repositories, technical documentation
FieldNote   — Practitioner posts: release notes, tool evals, benchmarks
              (Simon Willison, Lilian Weng, fast.ai, changelog posts)
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


# ── Enums ─────────────────────────────────────────────────────────────────────

class ContentType(str, Enum):
    talk    = "talk"
    article = "article"
    paper   = "paper"
    essay   = "essay"
    repo    = "repo"
    field   = "field"


class ShelfLife(str, Enum):
    days     = "days"       # pricing, benchmarks, release specifics
    months   = "months"     # tool comparisons, ecosystem state
    evergreen = "evergreen" # concepts, architecture, fundamentals


# ── Shared components ─────────────────────────────────────────────────────────

class ObsidianMetadata(BaseModel):
    """
    Rendered as YAML frontmatter in every note.
    Link fields (builds_on, see_also, contradicts) should be populated
    from a vault index passed in at invocation time — exact note titles only,
    no hallucination. Leave empty lists if no match is found.
    """
    tags:        list[str] = Field(
        description="Kebab-case topic tags, e.g. ['machine-learning', 'transformers']"
    )
    builds_on:   list[str] = Field(
        default_factory=list,
        description="Exact titles of vault notes this extends or depends on"
    )
    see_also:    list[str] = Field(
        default_factory=list,
        description="Exact titles of loosely related vault notes"
    )
    contradicts: list[str] = Field(
        default_factory=list,
        description="Exact titles of vault notes this challenges or conflicts with"
    )
    source_url:  HttpUrl
    source_type: ContentType
    ingested_on: date


class Reflection(BaseModel):
    """
    Personal interpretation block — rendered as ## Reflection in the note.
    All fields optional: the LLM should leave None rather than pad.
    """
    my_take:  Optional[str] = Field(
        default=None,
        description="Your reaction, agreement, or disagreement"
    )
    so_what:  Optional[str] = Field(
        default=None,
        description="Why this matters — implications for your work or thinking"
    )
    now_what: Optional[str] = Field(
        default=None,
        description="Concrete follow-up: action, experiment, or further reading"
    )


# ── Note types ────────────────────────────────────────────────────────────────

class TalkNote(BaseModel):
    """
    YouTube talks, conference presentations, expert lectures, podcasts.
    Routed from: youtube.com, vimeo.com, podcast feeds.
    """
    meta:       ObsidianMetadata
    title:      str
    speaker:    str
    venue:      Optional[str] = Field(
        default=None,
        description="Conference, podcast name, or platform"
    )
    thesis:     str = Field(
        description="The central claim in one sentence"
    )
    arguments:  list[str] = Field(
        description="Ordered supporting points — IEI spine"
    )
    key_quotes: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Verbatim memorable quotes, max 5"
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Questions this raises that are not answered"
    )
    reflection: Optional[Reflection] = None


class ArticleNote(BaseModel):
    """
    Blog posts, journalism, general web articles.
    Routed from: medium.com, and the long tail of domains.
    """
    meta:       ObsidianMetadata
    title:      str
    author:     Optional[str] = None
    thesis:     str = Field(
        description="The central argument or point in one sentence"
    )
    key_points: list[str] = Field(
        description="Main points made, in order"
    )
    evidence:   list[str] = Field(
        description="Data, studies, or examples cited in support"
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Questions this raises that are not answered"
    )
    reflection: Optional[Reflection] = None


class PaperNote(BaseModel):
    """
    Academic papers. Routed from: arxiv.org, doi.org, journal domains.
    Structure follows IMRaD convention.
    """
    meta:        ObsidianMetadata
    title:       str
    authors:     list[str]
    year:        Optional[int] = None
    hypothesis:  str = Field(
        description="The research question or hypothesis"
    )
    methodology: str = Field(
        description="How the study was conducted — one short paragraph"
    )
    findings:    list[str] = Field(
        description="Key results, in order of importance"
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Stated or apparent limitations of the work"
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Questions this raises that are not answered"
    )
    reflection: Optional[Reflection] = None


class EssayNote(BaseModel):
    """
    Opinion and long-form writing. Routed from: substack.com,
    personal blogs, and sites with strong authorial voice.
    Separates claimed assertions from evidenced ones.
    """
    meta:       ObsidianMetadata
    title:      str
    author:     Optional[str] = None
    thesis:     str = Field(
        description="The central opinion or argument in one sentence"
    )
    claimed:    list[str] = Field(
        description="Assertions made without hard evidence — opinion, intuition"
    )
    evidenced:  list[str] = Field(
        description="Assertions backed by data, examples, or citations"
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Questions this raises that are not answered"
    )
    reflection: Optional[Reflection] = None


class RepoNote(BaseModel):
    """
    GitHub repositories, libraries, technical documentation.
    Routed from: github.com, docs.* domains.
    """
    meta:          ObsidianMetadata
    name:          str
    what_it_does:  str = Field(
        description="One sentence description of purpose"
    )
    stack:         list[str] = Field(
        description="Languages, frameworks, key dependencies"
    )
    key_patterns:  list[str] = Field(
        description="Architectural or design patterns worth noting"
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Questions this raises that are not answered"
    )
    reflection: Optional[Reflection] = None


class FieldNote(BaseModel):
    """
    Practitioner field reports: model releases, tool evaluations,
    benchmark writeups, experiment logs.
    Examples: Simon Willison, Lilian Weng, fast.ai blog, changelog posts.
    Routed from: simonwillison.net, lilianweng.github.io, and similar.

    Key distinctions from ArticleNote:
    - authors_take is the *author's* informed opinion (a signal in itself)
    - data_points preserves specific numbers worth keeping
    - code_snippets preserves reproducible commands
    - shelf_life flags how quickly this will go stale
    """
    meta:          ObsidianMetadata
    title:         str
    author:        Optional[str] = None
    subject:       str = Field(
        description="The tool, model, or library this is about"
    )
    what_changed:  str = Field(
        description="The factual update or finding in one sentence"
    )
    data_points:   list[str] = Field(
        description="Specific numbers, benchmarks, prices worth preserving"
    )
    code_snippets: list[str] = Field(
        default_factory=list,
        description="Commands or code the author ran, verbatim"
    )
    authors_take:  Optional[str] = Field(
        default=None,
        description="The author's informed opinion — distinct from the facts"
    )
    shelf_life:    ShelfLife = Field(
        description="How quickly this will go stale"
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Questions this raises that are not answered"
    )
    reflection: Optional[Reflection] = None


# ── Union type for the router ─────────────────────────────────────────────────

AnyNote = TalkNote | ArticleNote | PaperNote | EssayNote | RepoNote | FieldNote


def note_to_slug(note: AnyNote, max_chars: int = 50) -> str:
    """Generate a short URL-safe slug from a note's title/name."""
    from slugify import slugify

    raw = getattr(note, "title", None) or getattr(note, "name", "untitled")
    return slugify(raw)[:max_chars].rstrip("-")


# ── URL routing (used by the agent router, not Pydantic) ─────────────────────
#
# Two-tier routing strategy:
#
# 1. UNAMBIGUOUS_DOMAINS — domain alone determines ContentType with certainty.
#    Skip LLM classification entirely for these.
#
# 2. MULTI_TYPE_DOMAINS — domain is known but individual articles vary in type.
#    Always send to LLM classifier. Guard rail: never add these to
#    UNAMBIGUOUS_DOMAINS, even if a pattern seems tempting.
#
# Everything else (unknown domains) also goes to LLM classification.
# Default fallback type if classification is uncertain: ContentType.article

UNAMBIGUOUS_DOMAINS: dict[str, ContentType] = {
    "youtube.com":          ContentType.talk,
    "youtu.be":             ContentType.talk,
    "vimeo.com":            ContentType.talk,
    "arxiv.org":            ContentType.paper,
    "doi.org":              ContentType.paper,
    "github.com":           ContentType.repo,
}

MULTI_TYPE_DOMAINS: set[str] = {
    # Official org blogs — article type varies per post
    "anthropic.com",
    "openai.com",
    "blog.google",
    "research.google",
    "deepmind.google",
    "ai.meta.com",
    "mistral.ai",
    # Practitioner blogs that mix essays, field notes, and articles
    "simonwillison.net",
    "lilianweng.github.io",
    "hamel.dev",
    "eugeneyan.com",
    "huyenchip.com",
    "substack.com",
}
