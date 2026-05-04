"""Write rendered notes to the Obsidian vault."""

import logging
from datetime import date
from pathlib import Path

from slugify import slugify

from src.config import settings
from src.exceptions import VaultWriteError

logger = logging.getLogger(__name__)


def make_filename(title: str) -> str:
    """Generate `{YYYY-MM-DD}_{slugified-title}.md`."""
    slug = slugify(title)
    return f"{date.today().isoformat()}_{slug}.md"


def write(filename: str, content: str) -> Path:
    """Write *content* to `{vault}/Inbox/{filename}`."""
    inbox = Path(settings.OBSIDIAN_VAULT_PATH) / "Inbox"
    path = inbox / filename
    try:
        inbox.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise VaultWriteError(f"Failed to write {path}: {exc}") from exc
    logger.info("Wrote note to %s", path)
    return path
