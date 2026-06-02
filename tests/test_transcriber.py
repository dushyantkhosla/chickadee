"""Tests for src/transcriber.py — mock at the boundary."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.exceptions import FetchError, ParseError
from src.models import YouTubeMetadata


@pytest.fixture
def mock_yt_metadata():
    return YouTubeMetadata(
        title="Test Video",
        channel="TestChannel",
        upload_date="20260515",
        view_count=1000,
        like_count=50,
        channel_follower_count=10000,
        categories=["Science & Technology"],
    )


class TestDownloadAudio:
    @patch("src.transcriber.yt_dlp.YoutubeDL")
    def test_success(self, mock_ydl_cls, mock_yt_metadata, tmp_path):
        audio_file = tmp_path / "download.m4a"
        audio_file.write_bytes(b"fake audio")

        mock_info = {
            "title": "Test Video",
            "channel": "TestChannel",
            "upload_date": "20260515",
            "view_count": 1000,
            "like_count": 50,
            "channel_follower_count": 10000,
            "categories": ["Science & Technology"],
        }
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        with patch("src.transcriber.tempfile.mkdtemp", return_value=str(tmp_path)):
            from src.transcriber import download_audio
            path, metadata = download_audio("https://www.youtube.com/watch?v=abc123")

        assert path.suffix == ".m4a"
        assert metadata.title == "Test Video"
        assert metadata.channel == "TestChannel"
        assert metadata.upload_date == "20260515"

    @patch("src.transcriber.yt_dlp.YoutubeDL")
    def test_download_error(self, mock_ydl_cls):
        import yt_dlp as yt_dlp_mod
        mock_ydl = MagicMock()
        mock_ydl.extract_info.side_effect = yt_dlp_mod.utils.DownloadError("geo-blocked")
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        from src.transcriber import download_audio
        with pytest.raises(FetchError, match="yt-dlp failed"):
            download_audio("https://www.youtube.com/watch?v=blocked")


class TestTranscribeAudio:
    @patch("src.transcriber._openrouter_chat")
    @patch("src.transcriber._audio_to_data_uri", return_value="data:audio/m4a;base64,abc")
    def test_success(self, mock_uri, mock_chat, tmp_path):
        audio_file = tmp_path / "test.m4a"
        audio_file.write_bytes(b"fake audio content")
        mock_chat.return_value = "This is the transcript."

        from src.transcriber import transcribe_audio
        result = transcribe_audio(audio_file)
        assert result == "This is the transcript."

    @patch("src.transcriber._openrouter_chat")
    @patch("src.transcriber._audio_to_data_uri", return_value="data:audio/m4a;base64,abc")
    def test_empty_transcription(self, mock_uri, mock_chat, tmp_path):
        audio_file = tmp_path / "test.m4a"
        audio_file.write_bytes(b"fake audio content")
        mock_chat.return_value = ""

        from src.transcriber import transcribe_audio
        with pytest.raises(ParseError, match="empty"):
            transcribe_audio(audio_file)


class TestFetchYouTubeTranscript:
    @patch("src.transcriber.transcribe_audio")
    @patch("src.transcriber.download_audio")
    def test_orchestration(self, mock_download, mock_transcribe, tmp_path):
        audio_file = tmp_path / "download.m4a"
        audio_file.write_bytes(b"fake audio")

        metadata = YouTubeMetadata(title="Test", channel="Ch")
        mock_download.return_value = (audio_file, metadata)
        mock_transcribe.return_value = "Hello world transcript"

        from src.transcriber import fetch_youtube_transcript
        transcript, meta = fetch_youtube_transcript("https://youtube.com/watch?v=abc")

        assert transcript == "Hello world transcript"
        assert meta.title == "Test"
        mock_transcribe.assert_called_once_with(audio_file)

    @patch("src.transcriber.transcribe_audio")
    @patch("src.transcriber.download_audio")
    def test_cleanup_on_failure(self, mock_download, mock_transcribe, tmp_path):
        audio_file = tmp_path / "download.m4a"
        audio_file.write_bytes(b"fake audio")

        metadata = YouTubeMetadata(title="Test", channel="Ch")
        mock_download.return_value = (audio_file, metadata)
        mock_transcribe.side_effect = ParseError("empty transcription")

        from src.transcriber import fetch_youtube_transcript
        with pytest.raises(ParseError):
            fetch_youtube_transcript("https://youtube.com/watch?v=abc")

        # Temp directory should be cleaned up by finally block
        assert not tmp_path.exists()
