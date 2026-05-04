"""CLI entrypoint: python -m src.main <url>"""

import argparse
import asyncio
import sys
from pathlib import Path

from src.agent import classify, summarise
from src.fetcher import fetch
from src.models import ContentType, note_to_slug
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


async def run_pipeline(url: str, dry_run: bool = False) -> Path | None:
    """Full pipeline: fetch → route/classify → index → summarise → render → write."""
    print(f"Fetching {url} ...")
    text = await fetch(url)
    print(f"Fetched {len(text.split())} words")

    content_type = await resolve_content_type(url, text)
    print(f"Resolved type: {content_type.value}")

    vault_titles = get_titles()
    print(f"Vault index: {len(vault_titles)} titles")

    note = await summarise(text, content_type, vault_titles, url)
    title = getattr(note, "title", getattr(note, "name", "untitled"))
    print(f"Summarised: {title}")

    markdown = render(note)
    print(f"Rendered {len(markdown)} chars")

    if dry_run:
        print("\n--- DRY RUN ---\n")
        print(markdown)
        return None

    filename = make_filename(note_to_slug(note))
    path = write(filename, markdown)
    print(f"Written to {path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Chickadee — structured summarisation")
    parser.add_argument("url", help="URL to summarise")
    parser.add_argument("--dry-run", action="store_true", help="Render without writing")
    args = parser.parse_args()

    try:
        asyncio.run(run_pipeline(args.url, dry_run=args.dry_run))
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
