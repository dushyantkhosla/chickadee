import tempfile
from pathlib import Path
from unittest.mock import patch

from src.vault_index import clear_cache, get_titles


def test_get_titles_collects_md_files():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "Note One.md").write_text("x")
        (Path(tmp) / "Note Two.md").write_text("y")
        (Path(tmp) / "Inbox").mkdir()
        (Path(tmp) / "Inbox" / "Draft.md").write_text("z")
        with patch("src.vault_index.settings.OBSIDIAN_VAULT_PATH", tmp):
            clear_cache()
            titles = get_titles()
            assert "Note One" in titles
            assert "Note Two" in titles
            assert "Draft" not in titles


def test_get_titles_uses_cache():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "A.md").write_text("x")
        with patch("src.vault_index.settings.OBSIDIAN_VAULT_PATH", tmp):
            clear_cache()
            first = get_titles()
            (Path(tmp) / "A.md").unlink()
            second = get_titles()
            assert first == second
            assert "A" in second
