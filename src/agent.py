"""PydanticAI agents for classification and summarisation."""

import logging

from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from datetime import date

from src.config import settings
from src.lmstudio_client import LMStudioClient
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

lm_client = LMStudioClient(
    settings.LM_STUDIO_BASE_URL,
    settings.LM_STUDIO_MODEL,
    settings.LM_STUDIO_API_KEY,
)


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

_classifier_agent = Agent(
    model=OpenAIChatModel(
        settings.LM_STUDIO_MODEL,
        provider=OpenAIProvider(
            base_url=settings.LM_STUDIO_BASE_URL,
            api_key="x",  # LM Studio does not require a real key
        ),
    ),
    model_settings=ModelSettings(temperature=0.0),
    output_type=ContentType,
    instructions=_CLASSIFIER_SYSTEM_PROMPT,
)


async def classify(text: str) -> ContentType:
    """Classify article text into a ContentType using a small local LLM.

    Falls back to ``ContentType.article`` if the LLM call fails.
    """
    await lm_client.ensure_model_loaded()
    try:
        result = await _classifier_agent.run(text[:4000])  # truncate to keep it fast
        return result.output
    except Exception as exc:
        logger.warning("Classifier LLM failed (%s), falling back to article", exc)
        return ContentType.article


# ── Summariser ──────────────────────────────────────────────────────────────

_CONTENT_TYPE_TO_MODEL = {
    ContentType.talk: TalkNote,
    ContentType.article: ArticleNote,
    ContentType.paper: PaperNote,
    ContentType.essay: EssayNote,
    ContentType.repo: RepoNote,
    ContentType.field: FieldNote,
}

_summariser_model = OpenAIChatModel(
    settings.LM_STUDIO_MODEL,
    provider=OpenAIProvider(
        base_url=settings.LM_STUDIO_BASE_URL,
        api_key="x",
    ),
)


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


async def summarise(
    text: str, content_type: ContentType, vault_titles: list[str], url: str
) -> AnyNote:
    """Summarise article text into a typed *Note using a local LLM."""
    await lm_client.ensure_model_loaded()
    note_type = _CONTENT_TYPE_TO_MODEL[content_type]
    agent = Agent(
        model=_summariser_model,
        output_type=note_type,
        model_settings=ModelSettings(temperature=0.2),
        instructions=_build_summariser_prompt(content_type, vault_titles, url),
    )
    result = await agent.run(text[:8000])
    return result.output
