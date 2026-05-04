import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.exceptions import VaultWriteError
from src.vault import make_filename, write


def test_write_creates_inbox_and_file():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("src.vault.settings.OBSIDIAN_VAULT_PATH", tmp):
            path = write("2026-05-04_test.md", "# Hello")
            assert path.exists()
            assert path.read_text() == "# Hello"
            assert path.parent.name == "Inbox"


def test_write_raises_on_bad_path():
    with patch("src.vault.settings.OBSIDIAN_VAULT_PATH", "/dev/null/readonly"):
        with pytest.raises(VaultWriteError):
            write("test.md", "content")


def test_make_filename():
    from datetime import date
    with patch("src.vault.date") as mock_date:
        mock_date.today.return_value = date(2026, 5, 4)
        assert make_filename("Hello World!") == "2026-05-04_hello-world.md"
