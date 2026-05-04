"""URL → ContentType routing based on domain."""

import logging
from urllib.parse import urlparse

from src.models import UNAMBIGUOUS_DOMAINS, MULTI_TYPE_DOMAINS, ContentType

logger = logging.getLogger(__name__)


def _extract_domain(url: str) -> str:
    """Extract the clean domain (no www, no path) from a URL."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def route(url: str) -> ContentType | None:
    """Return a concrete ContentType if the domain is unambiguous.

    Returns ``None`` when the URL needs LLM classification:
    - multi-type domains (e.g. substack.com, simonwillison.net)
    - unknown domains
    """
    domain = _extract_domain(url)

    if domain in UNAMBIGUOUS_DOMAINS:
        return UNAMBIGUOUS_DOMAINS[domain]

    if domain in MULTI_TYPE_DOMAINS:
        logger.warning(
            "Multi-type domain %s reached router — should be classified by LLM", domain
        )
        return None

    return None
