"""CLI entrypoint: python -m src.main <url>"""

import asyncio
import sys

from src.agent import classify
from src.models import ContentType
from src.router import route


async def resolve_content_type(url: str) -> ContentType:
    """Two-tier routing: domain first, LLM fallback."""
    content_type = route(url)
    if content_type is not None:
        return content_type
    # Fetch is not available yet (Epic 5); classify from a stub prompt for now.
    # Epic 4 wiring: classifier receives raw text. We pass a minimal stub
    # because fetcher integration happens in Epic 8.
    return await classify(f"Classify content from: {url}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m src.main <url>", file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1]
    content_type = asyncio.run(resolve_content_type(url))
    print(f"resolved: {content_type.value} for {url}")


if __name__ == "__main__":
    main()
