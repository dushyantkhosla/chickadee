from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.exceptions import FetchError, ParseError
from src.fetcher import fetch
from src.models import YouTubeMetadata


@pytest.mark.asyncio
async def test_fetch_html_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body><p>Hello world</p></body></html>"
    mock_response.raise_for_status = MagicMock()

    with patch("src.fetcher.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=False)
        client_instance.get = AsyncMock(return_value=mock_response)
        MockClient.return_value = client_instance

        with patch("src.fetcher.trafilatura.extract", return_value="Hello world"):
            text, metadata = await fetch("https://example.com/article")
            assert text == "Hello world"
            assert metadata is None


@pytest.mark.asyncio
async def test_fetch_html_404():
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found",
        request=MagicMock(),
        response=mock_response,
    )

    with patch("src.fetcher.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=False)
        client_instance.get = AsyncMock(return_value=mock_response)
        MockClient.return_value = client_instance

        with pytest.raises(FetchError, match="HTTP 404"):
            await fetch("https://example.com/missing")


@pytest.mark.asyncio
async def test_fetch_html_timeout():
    with patch("src.fetcher.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=False)
        client_instance.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        MockClient.return_value = client_instance

        with pytest.raises(FetchError, match="Timeout"):
            await fetch("https://example.com/slow")


@pytest.mark.asyncio
async def test_fetch_html_parse_error():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html></html>"
    mock_response.raise_for_status = MagicMock()

    with patch("src.fetcher.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=False)
        client_instance.get = AsyncMock(return_value=mock_response)
        MockClient.return_value = client_instance

        with patch("src.fetcher.trafilatura.extract", return_value=None):
            with pytest.raises(ParseError, match="Could not extract text"):
                await fetch("https://example.com/empty")


@pytest.mark.asyncio
async def test_fetch_youtube_success():
    metadata = YouTubeMetadata(title="Test Talk", channel="Speaker")
    mock_transcribe = MagicMock(return_value=("Hello world transcript", metadata))

    with patch("src.transcriber.fetch_youtube_transcript", mock_transcribe):
        text, meta = await fetch("https://www.youtube.com/watch?v=abc123")
        assert text == "Hello world transcript"
        assert meta.title == "Test Talk"
        assert meta.channel == "Speaker"


@pytest.mark.asyncio
async def test_fetch_youtube_mobile_subdomain():
    """Regression: m.youtube.com URLs must use the YouTube branch, not HTML extraction."""
    metadata = YouTubeMetadata(title="Mobile Talk", channel="Mobile Speaker")
    mock_transcribe = MagicMock(return_value=("Mobile transcript", metadata))

    with patch("src.transcriber.fetch_youtube_transcript", mock_transcribe):
        text, meta = await fetch("https://m.youtube.com/watch?v=abc123")
        assert text == "Mobile transcript"
        assert meta.title == "Mobile Talk"
        mock_transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_youtube_download_error():
    mock_transcribe = MagicMock(side_effect=FetchError("yt-dlp failed: geo-blocked"))

    with patch("src.transcriber.fetch_youtube_transcript", mock_transcribe):
        with pytest.raises(FetchError, match="yt-dlp failed"):
            await fetch("https://www.youtube.com/watch?v=blocked")


@pytest.mark.asyncio
async def test_fetch_youtube_transcription_empty():
    mock_transcribe = MagicMock(side_effect=ParseError("Transcription returned empty"))

    with patch("src.transcriber.fetch_youtube_transcript", mock_transcribe):
        with pytest.raises(ParseError, match="Transcription returned empty"):
            await fetch("https://www.youtube.com/watch?v=empty")
