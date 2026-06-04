import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.exceptions import VaultWriteError
from src.vault import make_filename, write


def test_write_creates_inbox_and_file():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("src.vault.settings.VAULT_BACKEND", "obsidian"), \
             patch("src.vault.settings.VAULT_PATH", tmp):
            path = write("2026-05-04_test.md", "# Hello")
            assert path.exists()
            assert path.read_text() == "# Hello"
            assert path.parent.name == "Inbox"


def test_write_raises_on_bad_path():
    with patch("src.vault.settings.VAULT_BACKEND", "obsidian"), \
         patch("src.vault.settings.VAULT_PATH", "/dev/null/readonly"):
        with pytest.raises(VaultWriteError):
            write("test.md", "content")


def test_make_filename():
    from datetime import date
    with patch("src.vault.settings.VAULT_BACKEND", "obsidian"), \
         patch("src.vault.date") as mock_date:
        mock_date.today.return_value = date(2026, 5, 4)
        assert make_filename("hello-world") == "2026-05-04_hello-world.md"


def test_write_logseq_creates_pages_and_file():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("src.vault.settings.VAULT_BACKEND", "logseq"), \
             patch("src.vault.settings.VAULT_PATH", tmp):
            path = write("test-article.md", "tags:: test\n\n# Hello")
            assert path.exists()
            assert path.read_text() == "tags:: test\n\n# Hello"
            assert path.parent.name == "pages"


def test_make_filename_logseq():
    with patch("src.vault.settings.VAULT_BACKEND", "logseq"):
        assert make_filename("hello-world") == "hello-world.md"
