"""Fetch and extract article text from URLs."""

import logging
from urllib.parse import urlparse

import httpx
import trafilatura
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

from src.exceptions import FetchError, ParseError

logger = logging.getLogger(__name__)


def _extract_youtube_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower().lstrip("www.")
    if host == "youtube.com":
        from urllib.parse import parse_qs
        query = parse_qs(parsed.query)
        if "v" in query:
            return query["v"][0]
    if host == "youtu.be":
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


def _fetch_transcript(video_id: str) -> str:
    try:
        transcript = YouTubeTranscriptApi().fetch(video_id)
    except (TranscriptsDisabled, NoTranscriptFound) as exc:
        raise ParseError(f"No transcript available for {video_id}") from exc
    except Exception as exc:
        raise FetchError(f"Transcript fetch failed for {video_id}: {exc}") from exc

    text = " ".join(seg.text for seg in transcript)
    if not text.strip():
        raise ParseError(f"Empty transcript for {video_id}")
    return text.strip()


async def fetch(url: str) -> str:
    """Fetch plain text from *url*.

    YouTube URLs are resolved via transcript API; everything else via
    httpx + trafilatura.
    """
    video_id = _extract_youtube_video_id(url)
    if video_id:
        text = _fetch_transcript(video_id)
    else:
        text = await _fetch_html(url)

    word_count = len(text.split())
    logger.info("Fetched %s — %d words", url, word_count)
    return text
