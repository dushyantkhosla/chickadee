"""CLI entrypoint: python -m src.main <url>"""

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

from src.agent import TalkMetadata, classify, summarise
from src.config import settings
from src.fetcher import fetch
from src.lmstudio_utils import unload_model
from src.models import AnyNote, ContentType, YouTubeMetadata, note_to_slug
from src.renderer import render
from src.router import route
from src.vault import make_filename, write
from src.vault_index import get_titles


async def resolve_content_type(url: str, text: str = "") -> ContentType:
    """Two-tier routing: domain first, LLM fallback."""
    content_type = route(url)
    if content_type is not None:
        return content_type
    return await classify(text or f"Classify content from: {url}")


def _parse_upload_date(raw: str | None) -> date | None:
    """Parse yt-dlp YYYYMMDD format to date object."""
    if not raw or len(raw) != 8:
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


async def run_pipeline(url: str, dry_run: bool = False) -> tuple[Path | None, AnyNote]:
    """Full pipeline: fetch → route/classify → index → summarise → render → write.

    Returns (path, note). path is None when dry_run=True.
    """
    try:
        print(f"Fetching {url} ...")
        text, yt_metadata = await fetch(url)
        print(f"Fetched {len(text.split())} words")

        content_type = await resolve_content_type(url, text)
        print(f"Resolved type: {content_type.value}")

        vault_titles = get_titles()
        print(f"Vault index: {len(vault_titles)} titles")

        # Build talk metadata from yt-dlp if available
        talk_deps = None
        if yt_metadata is not None and content_type == ContentType.talk:
            talk_deps = TalkMetadata(
                title=yt_metadata.title,
                speaker=yt_metadata.channel,
                categories=yt_metadata.categories,
                upload_date=_parse_upload_date(yt_metadata.upload_date),
            )

        note = await summarise(text, content_type, vault_titles, url, deps=talk_deps)

        # Inject upload_date into metadata if available
        if yt_metadata is not None:
            parsed_date = _parse_upload_date(yt_metadata.upload_date)
            if parsed_date:
                note.meta.upload_date = parsed_date

        title = getattr(note, "title", getattr(note, "name", "untitled"))
        print(f"Summarised: {title}")

        markdown = render(note)
        print(f"Rendered {len(markdown)} chars")

        if dry_run:
            print("\n--- DRY RUN ---\n")
            print(markdown)
            return None, note

        filename = make_filename(note_to_slug(note))
        path = write(filename, markdown)
        print(f"Written to {path}")
        return path, note
    finally:
        unload_model(settings.LM_STUDIO_MODEL)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chickadee — structured summarisation")
    parser.add_argument("url", help="URL to summarise")
    parser.add_argument("--dry-run", action="store_true", help="Render without writing")
    args = parser.parse_args()

    try:
        path, note = asyncio.run(run_pipeline(args.url, dry_run=args.dry_run))
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
