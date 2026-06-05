"""Write rendered notes to the vault — Obsidian (Inbox/) or Logseq (pages/)."""

import logging
from datetime import date
from pathlib import Path

from src.config import settings
from src.exceptions import VaultWriteError

logger = logging.getLogger(__name__)


def make_filename(slug: str) -> str:
    """Generate filename for the note. Obsidian: {date}_{slug}.md, Logseq: {slug}.md."""
    backend = getattr(settings, "VAULT_FORMAT", "obsidian")
    if backend == "logseq":
        return f"{slug}.md"
    return f"{date.today().isoformat()}_{slug}.md"


def write(filename: str, content: str) -> Path:
    """Write *content* to the vault. Obsidian: {vault}/Inbox/, Logseq: {vault}/pages/."""
    backend = getattr(settings, "VAULT_FORMAT", "obsidian")
    vault_root = Path(settings.VAULT_PATH)
    if backend == "logseq":
        target_dir = vault_root / "pages"
    else:
        target_dir = vault_root / "Inbox"
    path = target_dir / filename
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise VaultWriteError(f"Failed to write {path}: {exc}") from exc
    logger.info("Wrote note to %s", path)
    return path
