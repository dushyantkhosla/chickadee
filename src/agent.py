"""PydanticAI agents for classification and summarisation.

All LLM calls go through the provider chain (LM Studio → Vercel → free pool).
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from pydantic_ai import Agent, RunContext

from src.chain import call_with_fallback
from src.models import (
    AnyNote,
    ArticleNote,
    ContentType,
    EssayNote,
    FieldNote,
    PaperNote,
    RepoNote,
    TalkNote,
)

logger = logging.getLogger(__name__)

# ── Talk metadata (pre-populated from yt-dlp) ──────────────────────────────


@dataclass
class TalkMetadata:
    """Pre-populated metadata from yt-dlp. Passed as deps to the talk summariser."""
    title: str
    speaker: str
    categories: list[str]
    upload_date: Optional[date]


# ── Classifier ─────────────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM_PROMPT = """
You are a content classifier. Given an article's text, decide which of these
categories best describes the original piece:

- talk    : Conference talks, keynotes, podcasts, video lectures, presentations.
- article : Standard blog posts, journalism, news, how-to guides.
- paper   : Academic papers, preprints, research articles with IMRaD structure.
- essay   : Opinion pieces, long-form personal writing, Substack essays.
- repo    : GitHub repositories, code documentation, README-driven content.
- field   : Practitioner field reports: release notes, tool evals, benchmarks.

Respond with exactly one category. If uncertain, default to "article".
"""


async def classify(text: str) -> ContentType:
    """Classify article text into a ContentType.

    Falls back to ``ContentType.article`` if the LLM call fails.
    """
    result = await call_with_fallback(
        system_prompt=_CLASSIFIER_SYSTEM_PROMPT,
        user_prompt=text[:4000],
        output_type=ContentType,
        max_retries=3,
    )
    if result is None:
        logger.warning("Classification failed — all providers exhausted, defaulting to article")
        return ContentType.article
    return result


# ── Summariser ──────────────────────────────────────────────────────────────

_CONTENT_TYPE_TO_MODEL = {
    ContentType.talk: TalkNote,
    ContentType.article: ArticleNote,
    ContentType.paper: PaperNote,
    ContentType.essay: EssayNote,
    ContentType.repo: RepoNote,
    ContentType.field: FieldNote,
}


def _build_summariser_prompt(
    content_type: ContentType, vault_titles: list[str], url: str
) -> str:
    schema_name = _CONTENT_TYPE_TO_MODEL[content_type].__name__
    vault_section = ""
    if vault_titles:
        titles_text = "\n".join(f"- {t}" for t in vault_titles)
        vault_section = (
            f"Existing vault notes (exact titles):\n{titles_text}\n\n"
            "Populate builds_on, see_also, and contradicts using ONLY these exact titles. "
            "Leave empty if none match. Do not invent titles.\n"
        )
    return f"""You are a research assistant. Summarise the provided content into a structured {content_type.value} note.

Output must conform exactly to this Pydantic schema: {schema_name}

Rules:
- meta.source_url must be "{url}"
- meta.source_type must be "{content_type.value}"
- meta.ingested_on must be "{date.today().isoformat()}"
- meta.tags: kebab-case topic tags
- Reflection: always include a reflection object with individual fields set to null unless there is genuine insight. Do not set the entire reflection to null. Do not pad with generic text.
{vault_section}""".strip()


def _build_talk_prompt(vault_titles: list[str], url: str) -> str:
    """Simplified prompt for talk summarisation when metadata is pre-populated."""
    vault_section = ""
    if vault_titles:
        titles_text = "\n".join(f"- {t}" for t in vault_titles)
        vault_section = (
            f"Existing vault notes (exact titles):\n{titles_text}\n\n"
            "Populate builds_on, see_also, and contradicts using ONLY these exact titles. "
            "Leave empty if none match. Do not invent titles.\n"
        )
    return f"""You are a research assistant. Summarise the provided talk transcript into a structured talk note.

The title, speaker, and categories are provided via context — do NOT produce title or speaker fields.
Focus on: thesis, arguments, key_quotes, open_questions, and reflection.

Rules:
- meta.source_url must be "{url}"
- meta.source_type must be "talk"
- meta.ingested_on must be "{date.today().isoformat()}"
- meta.tags: kebab-case topic tags (seeded from the provided categories, refine as needed)
- Reflection: always include a reflection object with individual fields set to null unless there is genuine insight. Do not set the entire reflection to null. Do not pad with generic text.
{vault_section}""".strip()


def _inject_talk_metadata(ctx: RunContext[TalkMetadata]) -> str:
    """System-channel injection of talk metadata. PydanticAI concatenates
    this with the static instructions and sends it as the system message,
    so the LLM treats it as authoritative rather than as user data.
    """
    d = ctx.deps
    cats = ", ".join(d.categories) if d.categories else "none"
    return (
        f"Title: {d.title}\n"
        f"Speaker: {d.speaker}\n"
        f"Categories: {cats}\n"
        f"Upload date: {d.upload_date.isoformat() if d.upload_date else 'unknown'}"
    )


def _setup_talk_metadata(agent: Agent) -> None:
    """Attach the @agent.instructions callback that injects TalkMetadata
    via RunContext. Called by call_with_fallback after Agent construction
    but before agent.run().
    """
    agent.instructions(_inject_talk_metadata)


async def summarise(
    text: str,
    content_type: ContentType,
    vault_titles: list[str],
    url: str,
    deps: TalkMetadata | None = None,
) -> AnyNote:
    """Summarise content into a typed *Note using the provider chain.

    For talk notes with deps, attach _inject_talk_metadata to the Agent
    via the setup callback so TalkMetadata flows through the system channel
    via RunContext. For all other calls, the Agent has no deps.
    """
    note_type = _CONTENT_TYPE_TO_MODEL[content_type]

    if content_type == ContentType.talk and deps is not None:
        prompt = _build_talk_prompt(vault_titles, url)
    else:
        prompt = _build_summariser_prompt(content_type, vault_titles, url)

    user_prompt = text[:8000]
    use_deps = content_type == ContentType.talk and deps is not None

    result = await call_with_fallback(
        system_prompt=prompt,
        user_prompt=user_prompt,
        output_type=note_type,
        deps=deps if use_deps else None,
        deps_type=TalkMetadata if use_deps else None,
        setup=_setup_talk_metadata if use_deps else None,
        max_retries=3,
    )
    if result is None:
        raise RuntimeError(f"Summarisation failed — all providers exhausted for {url}")
    return result
