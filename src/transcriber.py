"""YouTube audio download and transcription.

Sync module — wrap calls with asyncio.to_thread() in async contexts.
Adapted from dk-transcribe-summarize skill.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import subprocess
import tempfile
import time
from pathlib import Path

import requests
import yt_dlp

from src.config import settings
from src.exceptions import FetchError, ParseError
from src.models import YouTubeMetadata

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def download_audio(url: str) -> tuple[Path, YouTubeMetadata]:
    """Download best audio from YouTube via yt-dlp.

    Returns (audio_path, metadata). Caller is responsible for cleanup.
    Raises FetchError on download failure.
    """
    tempdir = Path(tempfile.mkdtemp(prefix="yt_audio_"))
    outtmpl = str(tempdir / "download.%(ext)s")

    # Cookie strategy: prefer file (works in Docker), fallback to browser (local dev)
    cookie_file = Path("/app/cookies.txt")  # Docker path
    if not cookie_file.exists():
        cookie_file = Path(__file__).parent.parent / "cookies.txt"  # Local dev path

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
        "noplaylist": True,
        "quiet": True,
        **({"cookiefile": str(cookie_file)} if cookie_file.exists() else {"cookiesfrombrowser": ("brave",)}),
        "js_runtimes": {"node": {}},
        "remote_components": ["ejs:github"],
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "m4a", "preferredquality": "192"},
            {"key": "FFmpegMetadata", "add_metadata": True},
        ],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        raise FetchError(f"yt-dlp failed: {exc}") from exc

    # Find the resulting audio file
    candidates = (
        list(tempdir.glob("*.m4a"))
        or list(tempdir.glob("*.mp3"))
        or list(tempdir.glob("*.wav"))
        or list(tempdir.glob("*.webm"))
        or list(tempdir.glob("*.opus"))
    )
    if not candidates:
        raise FetchError(f"yt-dlp did not produce an audio file in {tempdir}")

    audio_path = candidates[0]
    title = info.get("title", audio_path.stem) if info else audio_path.stem
    channel = info.get("channel", "") if info else ""

    metadata = YouTubeMetadata(
        title=title,
        channel=channel,
        upload_date=info.get("upload_date") if info else None,
        view_count=info.get("view_count") if info else None,
        like_count=info.get("like_count") if info else None,
        channel_follower_count=info.get("channel_follower_count") if info else None,
        categories=info.get("categories", []) if info else [],
    )

    logger.info("Downloaded audio: %s (%s)", title, audio_path.name)
    return audio_path, metadata


def _compress_audio(path: Path) -> Path:
    """Re-encode audio to a small speech-optimized MP3 for API upload."""
    out_path = path.with_suffix(".compressed.mp3")
    cmd = [
        "ffmpeg", "-y", "-i", str(path),
        "-vn", "-ar", "16000", "-ac", "1",
        "-codec:a", "libmp3lame", "-b:a", "8k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def _audio_to_data_uri(path: Path) -> str:
    """Encode audio file as a base64 data URI for multimodal API calls."""
    mime, _ = mimetypes.guess_type(str(path))
    if mime is None:
        ext = path.suffix.lower()
        mime = {
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".wav": "audio/wav",
        }.get(ext, "audio/mpeg")
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode()
    return f"data:{mime};base64,{b64}"


def _openrouter_chat(messages: list, max_tokens: int = 10000, temperature: float = 0) -> str:
    """Call OpenRouter API with retry logic."""
    api_key = settings.OPENROUTER_API_KEY
    if not api_key:
        raise FetchError("OPENROUTER_API_KEY is not set")

    last_err = None
    for attempt in range(1, 6):
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.TRANSCRIPTION_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=300,
        )
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.ok and "choices" in data and data["choices"]:
            break
        err_msg = (
            data.get("error", {}).get("message", resp.text[:300])
            if isinstance(data.get("error"), dict)
            else str(data.get("error", resp.text[:300]))
        )
        last_err = f"HTTP {resp.status_code}: {err_msg}"
        logger.warning("OpenRouter attempt %d/5 failed: %s", attempt, last_err)
        if attempt < 5:
            wait = 10 * attempt
            time.sleep(wait)
    else:
        raise FetchError(f"OpenRouter transcription failed after 5 attempts: {last_err}")

    msg = data["choices"][0]["message"]
    content = msg.get("content") or msg.get("reasoning") or ""
    for prefix in ("Transcription:", "Transcript:", "Here is the transcription:"):
        if content.startswith(prefix):
            content = content[len(prefix):]
            break
    return content.strip()


def transcribe_audio(audio_path: Path) -> str:
    """Transcribe audio via OpenRouter multimodal API.

    Returns transcription text. Raises ParseError on empty result,
    FetchError on API errors.
    """
    raw_size = audio_path.stat().st_size
    estimated_b64 = raw_size * 4 // 3
    if estimated_b64 > 6_000_000:
        logger.info("Audio is large (%d bytes), compressing for API upload...", raw_size)
        audio_path = _compress_audio(audio_path)

    data_uri = _audio_to_data_uri(audio_path)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "audio_url", "audio_url": {"url": data_uri}},
                {
                    "type": "text",
                    "text": "Transcribe this audio. Output only the transcription, no commentary.",
                },
            ],
        }
    ]
    transcript = _openrouter_chat(messages, max_tokens=10000)
    if not transcript.strip():
        raise ParseError("Transcription returned empty")
    return transcript


def fetch_youtube_transcript(url: str) -> tuple[str, YouTubeMetadata]:
    """Download audio from YouTube and transcribe it.

    Returns (transcript_text, metadata). Cleans up temp files.
    Raises FetchError or ParseError on failure.
    """
    audio_path = None
    tempdir = None
    try:
        audio_path, metadata = download_audio(url)
        tempdir = audio_path.parent
        logger.info("Transcribing %s ...", metadata.title)
        transcript = transcribe_audio(audio_path)
        logger.info("Transcribed %s — %d words", metadata.title, len(transcript.split()))
        return transcript, metadata
    finally:
        if tempdir and tempdir.exists():
            import shutil
            shutil.rmtree(tempdir, ignore_errors=True)
