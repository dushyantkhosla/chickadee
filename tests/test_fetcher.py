from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.exceptions import FetchError, ParseError
from src.fetcher import fetch


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
            result = await fetch("https://example.com/article")
            assert result == "Hello world"


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
    mock_transcript = MagicMock()
    mock_transcript.__iter__ = MagicMock(return_value=iter([
        MagicMock(text="Hello"),
        MagicMock(text="world"),
    ]))

    with patch("src.fetcher.YouTubeTranscriptApi") as MockApi:
        mock_instance = MagicMock()
        mock_instance.fetch = MagicMock(return_value=mock_transcript)
        MockApi.return_value = mock_instance

        result = await fetch("https://www.youtube.com/watch?v=abc123")
        assert result == "Hello world"


@pytest.mark.asyncio
async def test_fetch_youtube_no_transcript():
    from youtube_transcript_api._errors import TranscriptsDisabled

    with patch("src.fetcher.YouTubeTranscriptApi") as MockApi:
        mock_instance = MagicMock()
        mock_instance.fetch = MagicMock(side_effect=TranscriptsDisabled("abc123"))
        MockApi.return_value = mock_instance

        with pytest.raises(ParseError, match="No transcript available"):
            await fetch("https://youtu.be/abc123")
