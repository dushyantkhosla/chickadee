"""Fetch and extract article text from URLs."""

import asyncio
import logging
from typing import Optional

import httpx
import trafilatura

from src.exceptions import FetchError, ParseError
from src.models import YouTubeMetadata

logger = logging.getLogger(__name__)


def _extract_youtube_video_id(url: str) -> str | None:
    """Check if URL is a YouTube video. Used for routing, not fetching."""
    from urllib.parse import parse_qs, urlparse
    parsed = urlparse(url)
    host = parsed.netloc.lower().lstrip("www.").lstrip("m.")
    if host in ("youtube.com", "youtu.be"):
        if host == "youtube.com":
            query = parse_qs(parsed.query)
            if "v" in query:
                return query["v"][0]
        else:
            return parsed.path.lstrip("/").split("/")[0]
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
