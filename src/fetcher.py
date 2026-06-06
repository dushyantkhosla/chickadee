"""Fetch and extract article text from URLs."""

import asyncio
import logging
from typing import Optional

import httpx
import trafilatura

from src.exceptions import FetchError, ParseError
from src.models import YouTubeMetadata

logger = logging.getLogger(__name__)


_YOUTUBE_REGISTERED_DOMAINS = frozenset({"youtube.com", "youtu.be", "youtube-nocookie.com"})


def _is_youtube_host(host: str) -> bool:
    """Return True if *host* belongs to a known YouTube registered domain.

    Uses the last two labels (the registered domain) so that:
    - All subdomains (m., www., music., accounts., studio., etc.) match
    - Suffix attacks like 'youtube.com.evil.com' are rejected
    - Unrelated domains containing 'youtube' as a substring (notyoutube.com) are rejected
    """
    parts = host.lower().split(".")
    if len(parts) < 2:
        return False
    return ".".join(parts[-2:]) in _YOUTUBE_REGISTERED_DOMAINS


def _extract_youtube_video_id(url: str) -> str | None:
    """Check if URL is a YouTube video. Used for routing, not fetching."""
    from urllib.parse import parse_qs, urlparse
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not _is_youtube_host(host):
        return None
    if host.endswith("youtu.be"):
        segments = parsed.path.lstrip("/").split("/")
        return segments[0] or None
    path_segments = parsed.path.lstrip("/").split("/")
    if len(path_segments) >= 2 and path_segments[0] == "embed":
        return path_segments[1] or None
    query = parse_qs(parsed.query)
    if "v" in query and query["v"]:
        return query["v"][0]
    return None


async def _fetch_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FetchError(f"HTTP {exc.response.status_code} for {url}") from exc
        except httpx.TimeoutException as exc:
            raise FetchError(f"Timeout fetching {url}") from exc
        except httpx.RequestError as exc:
            raise FetchError(f"Request failed for {url}: {exc}") from exc

        html = resp.text
        text = trafilatura.extract(html, include_comments=False, include_tables=False)
        if text is None or not text.strip():
            raise ParseError(f"Could not extract text from {url}")
        return text.strip()


async def fetch(url: str) -> tuple[str, Optional[YouTubeMetadata]]:
    """Fetch plain text from *url*.

    YouTube URLs are resolved via yt-dlp audio download + transcription;
    everything else via httpx + trafilatura.

    Returns (text, metadata). metadata is only set for YouTube URLs.
    """
    from src.transcriber import fetch_youtube_transcript

    video_id = _extract_youtube_video_id(url)
    if video_id:
        transcript, metadata = await asyncio.to_thread(
            fetch_youtube_transcript, url
        )
        word_count = len(transcript.split())
        logger.info("Fetched %s — %d words (via audio transcription)", url, word_count)
        return transcript, metadata
    else:
        text = await _fetch_html(url)
        word_count = len(text.split())
        logger.info("Fetched %s — %d words", url, word_count)
        return text, None
