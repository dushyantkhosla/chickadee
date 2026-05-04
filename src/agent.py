"""PydanticAI agents for classification and summarisation."""

import logging

from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.config import settings
from src.models import ContentType

logger = logging.getLogger(__name__)

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
    try:
        result = await _classifier_agent.run(text[:4000])  # truncate to keep it fast
        return result.output
    except Exception as exc:
        logger.warning("Classifier LLM failed (%s), falling back to article", exc)
        return ContentType.article
