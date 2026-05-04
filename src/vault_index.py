"""Read existing note titles from the Obsidian vault."""

import logging
import time
from pathlib import Path

from src.config import settings

logger = logging.getLogger(__name__)

_ttl_seconds = 60
_last_fetch = 0.0
_cached_titles: list[str] = []


def get_titles() -> list[str]:
    """Return sorted vault note titles (excluding Inbox), cached for 60s."""
    global _last_fetch, _cached_titles
    now = time.monotonic()
    if now - _last_fetch < _ttl_seconds and _cached_titles:
        return _cached_titles

    vault = Path(settings.OBSIDIAN_VAULT_PATH)
    titles: list[str] = []
    if vault.exists():
        for path in vault.rglob("*.md"):
            if path.parent.name == "Inbox":
                continue
            titles.append(path.stem)

    _cached_titles = sorted(titles)
    _last_fetch = now
    logger.debug("Indexed %d vault titles", len(_cached_titles))
    return _cached_titles


def clear_cache() -> None:
    """Reset the title cache (useful in tests)."""
    global _last_fetch, _cached_titles
    _last_fetch = 0
    _cached_titles = []
