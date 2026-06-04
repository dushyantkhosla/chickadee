# Dual-Backend Vault Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support both Obsidian and Logseq as vault backends, selected via `VAULT_BACKEND` env var. Users self-host everything on a cheap VPS — Chickadee writes notes, user picks their preferred note UI.

**Architecture:** Single codebase with conditional rendering and writing. The `render()` function checks `VAULT_BACKEND` and produces either YAML frontmatter (Obsidian) or `property:: value` lines (Logseq). The `write()` function writes to `Inbox/` (Obsidian) or `pages/` (Logseq). The vault index scans different directories per backend. All LLM prompts, agent logic, and body rendering stay unchanged.

**Tech Stack:** Python, Pydantic, PyYAML (existing), python-slugify (existing)

**Self-hosting options:**
- **Logseq:** `ghcr.io/logseq/logseq-webapp` — lightweight web app, ~100MB RAM
- **Obsidian:** `lscr.io/linuxserver/obsidian` — full desktop, ~1GB RAM
- Both read from the same vault directory that Chickadee writes to

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Backend selection | `VAULT_BACKEND` env var (`obsidian` default) | Backward compatible, single config point |
| Backend validation | `Literal["obsidian", "logseq"]` | Prevents silent misbehavior from typos |
| Class rename | `ObsidianMetadata` → `VaultMetadata` | Accurate name, mechanical rename |
| Renderer architecture | Single `renderer.py` with conditional | Only ~20 lines differ, body is shared |
| Vault writer | Single `vault.py` with conditional | Only directory and filename differ |
| File naming | Obsidian: `{date}_{slug}.md`, Logseq: `{slug}.md` | Obsidian users may rely on date排序; Logseq uses `ingested-on::` property |
| Vault index | Branch on backend | Different scan directories |
| Empty properties | Omit in Logseq | Logseq ignores empty properties |
| Bot confirmation | Show filename only | Folder path is implementation detail |
| REST API removal | Drop `OBSIDIAN_API_KEY`, `OBSIDIAN_BASE_URL` | Option A (REST API plugin) is unused; filesystem write (Option B) is simpler and works for both backends |

---

## File Structure

| File | Change |
|------|--------|
| `src/config.py` | Add `VAULT_BACKEND`, rename `OBSIDIAN_VAULT_PATH` → `VAULT_PATH`, remove unused API vars |
| `src/models.py` | Rename `ObsidianMetadata` → `VaultMetadata`, update docstring |
| `src/renderer.py` | Add `_render_properties()` for Logseq, update `render()` to branch on backend |
| `src/vault.py` | Add `make_filename_logseq()`, update `write()` to branch on backend |
| `src/vault_index.py` | Branch scan logic: `pages/` for Logseq, vault root minus `Inbox/` for Obsidian |
| `src/bot.py` | Remove `INBOX_PREFIX`, show filename only in confirmation, update help text |
| `docker-compose.yml` | Rename env vars, remove unused API vars |
| `.env.example` | Rename env vars, remove unused API vars |
| `tests/test_vault.py` | Add Logseq write test, update make_filename test |
| `tests/test_vault_index.py` | Add Logseq index test, update patches |
| `tests/test_renderer.py` | Add Logseq property tests, update ObsidianMetadata → VaultMetadata |
| `tests/test_config.py` | Update VAULT_PATH, add VAULT_BACKEND tests |
| `tests/test_integration.py` | Update patches and imports |
| `tests/test_bot.py` | Update imports, update confirmation assertion |
| `tests/test_models.py` | Update imports |
| `tests/test_summariser.py` | Update imports |
| `AGENTS.md` | Update `ObsidianMetadata` → `VaultMetadata`, vault env var names, remove REST API option |
| `README.md` | Update Obsidian-specific language, env var names |
| `DESIGN.md` | Update `OBSIDIAN_VAULT_PATH` reference |
| `docs/adr/0001-logseq-vault-backend.md` | Decision record |
| Docker services | Logseq web app OR Obsidian desktop (user picks one) |

---

### Task 1: Config changes

**Files:**

- Modify: `src/config.py:42-45`
- Modify: `tests/test_config.py:10-14,17-25`

- [ ] **Step 1: Write the failing test**

In `tests/test_config.py`, add a test for `VAULT_BACKEND` (add `import pytest` to imports if not present):

```python
def test_config_vault_backend_default():
    with patch.dict(os.environ, {}, clear=True):
        s = Settings(_env_file=None)
        assert s.VAULT_BACKEND == "obsidian"


def test_config_vault_backend_logseq():
    with patch.dict(os.environ, {"VAULT_BACKEND": "logseq"}, clear=False):
        s = Settings(_env_file=None)
        assert s.VAULT_BACKEND == "logseq"


def test_config_vault_backend_invalid():
    with patch.dict(os.environ, {"VAULT_BACKEND": "notavalid"}, clear=False):
        with pytest.raises(Exception):  # ValidationError
            Settings(_env_file=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_config_vault_backend_default -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'VAULT_BACKEND'`

- [ ] **Step 3: Update config**

Replace lines 42-45 in `src/config.py`:

```python
    # ── Vault ────────────────────────────────────────────────────────────
    VAULT_BACKEND: Literal["obsidian", "logseq"] = "obsidian"
    VAULT_PATH: str = "/tmp/chickadee-vault"
```

Note: Add `from typing import Literal` to the imports at the top of `config.py`. The `Literal` constraint prevents silent misbehavior from typos like `VAULT_BACKEND=foo`.

- [ ] **Step 4: Update existing config tests**

Replace `OBSIDIAN_VAULT_PATH` with `VAULT_PATH` in `tests/test_config.py`:

```python
def test_config_loads_from_env():
    s = Settings(
        VAULT_PATH="/custom/vault",
    )
    assert s.VAULT_PATH == "/custom/vault"


def test_config_loads_from_dotenv():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("VAULT_PATH=/dotenv/vault\n")
        f.flush()
        path = f.name

    try:
        s = Settings(_env_file=path)
        assert s.VAULT_PATH == "/dotenv/vault"
    finally:
        os.unlink(path)
```

- [ ] **Step 5: Run all config tests**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add VAULT_BACKEND and VAULT_PATH config, remove unused OBSIDIAN_* vars"
```

---

### Task 2: Rename ObsidianMetadata → VaultMetadata

**Files:**

- Modify: `src/models.py:7,50-55,107,133,157,187,211,242`
- Modify: `tests/test_renderer.py:11,29`
- Modify: `tests/test_models.py:8,19`
- Modify: `tests/test_bot.py:18,21,43`
- Modify: `tests/test_integration.py:11,16`
- Modify: `tests/test_summariser.py:14,24`

- [ ] **Step 1: Write the failing test**

No new test needed — existing tests will fail after rename, proving the rename was applied.

- [ ] **Step 2: Rename in models.py**

In `src/models.py`, use find-and-replace:
- Replace `ObsidianMetadata` with `VaultMetadata` (all occurrences)
- Update docstring on line 7: `All notes embed VaultMetadata (vault housekeeping)`
- Update docstring on line 51: `Rendered as vault metadata in every note.`

- [ ] **Step 3: Update all test imports**

In each test file, replace `ObsidianMetadata` with `VaultMetadata`:

`tests/test_renderer.py` line 11: `VaultMetadata,`
`tests/test_renderer.py` line 29: `return VaultMetadata(**defaults)`
`tests/test_models.py` line 8: `VaultMetadata,`
`tests/test_models.py` line 19: `return VaultMetadata(`
`tests/test_bot.py` line 18: `from src.models import ArticleNote, VaultMetadata, ContentType`
`tests/test_bot.py` line 21: `meta=VaultMetadata(`
`tests/test_bot.py` line 43: `from src.models import RepoNote, VaultMetadata, ContentType`
`tests/test_bot.py` line 46: `meta=VaultMetadata(`
`tests/test_integration.py` line 11: `from src.models import ArticleNote, ContentType, VaultMetadata, Reflection`
`tests/test_integration.py` line 16: `meta=VaultMetadata(`
`tests/test_summariser.py` line 14: `VaultMetadata,`
`tests/test_summariser.py` line 24: `return VaultMetadata(`

- [ ] **Step 4: Run all tests**

Run: `pytest tests/ -v`
Expected: PASS (all tests using VaultMetadata)

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/
git commit -m "refactor: rename ObsidianMetadata to VaultMetadata"
```

---

### Task 3: Logseq renderer

**Files:**

- Modify: `src/renderer.py:1-34`
- Create: `tests/test_renderer_logseq.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_renderer_logseq.py`:

```python
"""Tests for Logseq property rendering."""
from datetime import date
from unittest.mock import patch

from src.models import (
    ArticleNote,
    ContentType,
    VaultMetadata,
    Reflection,
    TalkNote,
)
from src.renderer import render


def _meta(**kwargs):
    defaults = dict(
        tags=["machine-learning"],
        source_url="https://example.com/article",
        source_type=ContentType.article,
        ingested_on=date(2026, 5, 4),
    )
    defaults.update(kwargs)
    return VaultMetadata(**defaults)


def test_logseq_properties_format():
    note = ArticleNote(
        meta=_meta(
            builds_on=["Prior Work"],
            see_also=["Related"],
        ),
        title="Test Article",
        author="Alice",
        thesis="Testing is good",
        key_points=["Point A"],
        evidence=["Study X"],
        open_questions=[],
        reflection=Reflection(),
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "logseq"
        md = render(note)
    assert md.startswith("tags:: machine-learning")
    assert "builds-on:: [[Prior Work]]" in md
    assert "see-also:: [[Related]]" in md
    assert "source-url:: https://example.com/article" in md
    assert "source-type:: article" in md
    assert "ingested-on:: 2026-05-04" in md
    assert "---" not in md  # No YAML frontmatter


def test_logseq_omits_empty_properties():
    note = ArticleNote(
        meta=_meta(),
        title="Sparse",
        author="Bob",
        thesis="Sparse",
        key_points=[],
        evidence=[],
        open_questions=[],
        reflection=Reflection(),
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "logseq"
        md = render(note)
    assert "builds-on::" not in md
    assert "see-also::" not in md
    assert "contradicts::" not in md


def test_logseq_upload_date_property():
    note = ArticleNote(
        meta=_meta(upload_date=date(2026, 3, 15)),
        title="Dated Article",
        thesis="Has upload date",
        key_points=[],
        evidence=[],
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "logseq"
        md = render(note)
    assert "upload-date:: 2026-03-15" in md


def test_logseq_body_unchanged():
    note = TalkNote(
        meta=_meta(source_type=ContentType.talk),
        title="A Talk",
        speaker="Alice",
        thesis="Talk thesis",
        arguments=["Arg 1"],
        key_quotes=["Quote 1"],
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "logseq"
        md = render(note)
    assert "# A Talk" in md
    assert "## Summary" in md
    assert "## Arguments" in md
    assert "> Quote 1" in md


def test_logseq_contradicts_property():
    note = ArticleNote(
        meta=_meta(contradicts=["Flawed Study"]),
        title="Refutation",
        thesis="Opposing view",
        key_points=[],
        evidence=[],
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "logseq"
        md = render(note)
    assert "contradicts:: [[Flawed Study]]" in md


def test_logseq_multiple_tags():
    note = ArticleNote(
        meta=_meta(tags=["ml", "python", "research"]),
        title="Multi-tag",
        thesis="Tags test",
        key_points=[],
        evidence=[],
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "logseq"
        md = render(note)
    assert "tags:: ml, python, research" in md


def test_logseq_multiple_builds_on():
    note = ArticleNote(
        meta=_meta(builds_on=["Note A", "Note B"]),
        title="Multi-link",
        thesis="Links test",
        key_points=[],
        evidence=[],
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "logseq"
        md = render(note)
    assert "builds-on:: [[Note A]], [[Note B]]" in md


def test_render_obsidian_backend_produces_yaml_frontmatter():
    note = ArticleNote(
        meta=_meta(),
        title="Obsidian Backend",
        thesis="YAML frontmatter test",
        key_points=[],
        evidence=[],
    )
    with patch("src.renderer.settings") as mock_settings:
        mock_settings.VAULT_BACKEND = "obsidian"
        md = render(note)
    assert md.startswith("---")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_renderer_logseq.py -v`
Expected: FAIL with import error or assertion error

- [ ] **Step 3: Implement Logseq rendering**

In `src/renderer.py`, make these changes:

1. Replace the docstring (line 1): `"Obsidian-compatible"` → `"Obsidian or Logseq"`
2. Add `from src.config import settings` to imports (line 3, after `import yaml`)
3. Replace the `render()` function (lines 16-19) with the conditional version below
4. Replace the `_render_frontmatter()` function (lines 22-34) with the updated version below
5. Add the new `_render_properties()` function after `_render_frontmatter()`
6. **Do NOT touch** `_render_body()` (line 37) or any of the type-specific renderers — those stay exactly as they are

The complete replacement for the top section of the file (lines 1-34):

```python
"""Render AnyNote to Markdown — Obsidian (YAML frontmatter) or Logseq (properties)."""

from src.config import settings
from src.models import (
    AnyNote,
    ArticleNote,
    EssayNote,
    FieldNote,
    PaperNote,
    RepoNote,
    TalkNote,
)


def render(note: AnyNote) -> str:
    backend = getattr(settings, "VAULT_BACKEND", "obsidian")
    if backend == "logseq":
        header = _render_properties(note.meta)
    else:
        header = f"---\n{_render_frontmatter(note.meta)}---"
    body = _render_body(note)
    return f"{header}\n\n{body}"


def _render_frontmatter(meta) -> str:
    import yaml
    data = {
        "tags": meta.tags,
        "builds_on": [f"[[{t}]]" for t in meta.builds_on],
        "see_also": [f"[[{t}]]" for t in meta.see_also],
        "contradicts": [f"[[{t}]]" for t in meta.contradicts],
        "source_url": str(meta.source_url),
        "source_type": meta.source_type.value,
        "ingested_on": meta.ingested_on.isoformat(),
    }
    if meta.upload_date is not None:
        data["upload_date"] = meta.upload_date.isoformat()
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _render_properties(meta) -> str:
    """Render VaultMetadata as Logseq property lines."""
    lines = []
    if meta.tags:
        lines.append(f"tags:: {', '.join(meta.tags)}")
    if meta.builds_on:
        links = ", ".join(f"[[{t}]]" for t in meta.builds_on)
        lines.append(f"builds-on:: {links}")
    if meta.see_also:
        links = ", ".join(f"[[{t}]]" for t in meta.see_also)
        lines.append(f"see-also:: {links}")
    if meta.contradicts:
        links = ", ".join(f"[[{t}]]" for t in meta.contradicts)
        lines.append(f"contradicts:: {links}")
    lines.append(f"source-url:: {meta.source_url}")
    lines.append(f"source-type:: {meta.source_type.value}")
    lines.append(f"ingested-on:: {meta.ingested_on.isoformat()}")
    if meta.upload_date is not None:
        lines.append(f"upload-date:: {meta.upload_date.isoformat()}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run Logseq tests**

Run: `pytest tests/test_renderer_logseq.py -v`
Expected: PASS

- [ ] **Step 5: Patch Obsidian renderer tests**

After the `render()` change, existing Obsidian renderer tests (`tests/test_renderer.py`) now read `settings.VAULT_BACKEND` — if the developer has `VAULT_BACKEND=logseq` in their environment, these tests will get Logseq format and fail. Add a `VAULT_BACKEND` patch to each test that asserts Obsidian-specific formatting (YAML frontmatter, `---` delimiters).

Add this import at the top of `tests/test_renderer.py` (next to existing `from unittest.mock import patch` — or add it if `patch` isn't already imported):

```python
from unittest.mock import patch
```

Then add `@patch("src.renderer.settings.VAULT_BACKEND", "obsidian")` as a decorator to every test in the file. Example for `test_render_article_note`:

```python
@patch("src.renderer.settings.VAULT_BACKEND", "obsidian")
def test_render_article_note():
    ...
```

Apply the same decorator to all 8 tests: `test_render_article_note`, `test_render_omits_empty_open_questions`, `test_render_omits_none_reflection_fields`, `test_render_talk_note_with_quotes`, `test_render_paper_note`, `test_render_essay_note`, `test_render_repo_note`, `test_render_field_note_special_sections`.

- [ ] **Step 6: Run all renderer tests**

Run: `pytest tests/test_renderer.py tests/test_renderer_logseq.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/renderer.py tests/test_renderer.py tests/test_renderer_logseq.py
git commit -m "feat: add Logseq property rendering alongside Obsidian YAML frontmatter"
```

---

### Task 4: Vault writer — Logseq pages/ directory

**Files:**

- Modify: `src/vault.py:1-28`
- Modify: `tests/test_vault.py:1-30`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_vault.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_vault.py::test_write_logseq_creates_pages_and_file -v`
Expected: FAIL (writes to Inbox/ not pages/)

- [ ] **Step 3: Update vault.py**

Replace `src/vault.py` entirely:

```python
"""Write rendered notes to the vault — Obsidian (Inbox/) or Logseq (pages/)."""

import logging
from datetime import date
from pathlib import Path

from src.config import settings
from src.exceptions import VaultWriteError

logger = logging.getLogger(__name__)


def make_filename(slug: str) -> str:
    """Generate filename for the note. Obsidian: {date}_{slug}.md, Logseq: {slug}.md."""
    backend = getattr(settings, "VAULT_BACKEND", "obsidian")
    if backend == "logseq":
        return f"{slug}.md"
    return f"{date.today().isoformat()}_{slug}.md"


def write(filename: str, content: str) -> Path:
    """Write *content* to the vault. Obsidian: {vault}/Inbox/, Logseq: {vault}/pages/."""
    backend = getattr(settings, "VAULT_BACKEND", "obsidian")
    vault_root = Path(settings.VAULT_PATH)
    if backend == "logseq":
        target_dir = vault_root / "pages"
    else:
        target_dir = vault_root / "Inbox"
    path = target_dir / filename
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise VaultWriteError(f"Failed to write {path}: {exc}") from exc
    logger.info("Wrote note to %s", path)
    return path
```

- [ ] **Step 4: Update existing Obsidian test patches**

In `tests/test_vault.py`, update patches from `OBSIDIAN_VAULT_PATH` to `VAULT_PATH`:

```python
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
```

- [ ] **Step 5: Run all vault tests**

Run: `pytest tests/test_vault.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/vault.py tests/test_vault.py
git commit -m "feat: support Logseq pages/ directory and slug-only filenames"
```

---

### Task 5: Vault index — branch on backend

**Files:**

- Modify: `src/vault_index.py:16-34`
- Modify: `tests/test_vault_index.py:1-31`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_vault_index.py`:

```python
def test_logseq_get_titles_scans_pages():
    with tempfile.TemporaryDirectory() as tmp:
        pages = Path(tmp) / "pages"
        pages.mkdir()
        (pages / "Note One.md").write_text("x")
        (pages / "Note Two.md").write_text("y")
        with patch("src.vault_index.settings.VAULT_BACKEND", "logseq"), \
             patch("src.vault_index.settings.VAULT_PATH", tmp):
            clear_cache()
            titles = get_titles()
            assert "Note One" in titles
            assert "Note Two" in titles
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_vault_index.py::test_logseq_get_titles_scans_pages -v`
Expected: FAIL (scans root, not pages/)

- [ ] **Step 3: Update vault_index.py**

Replace `src/vault_index.py` lines 16-34:

```python
def get_titles() -> list[str]:
    """Return sorted vault note titles, cached for 60s.
    Obsidian: scans vault root, excludes Inbox/.
    Logseq: scans pages/ directory.
    """
    global _last_fetch, _cached_titles
    now = time.monotonic()
    if now - _last_fetch < _ttl_seconds and _cached_titles:
        return _cached_titles

    vault = Path(settings.VAULT_PATH)
    backend = getattr(settings, "VAULT_BACKEND", "obsidian")
    titles: list[str] = []

    if backend == "logseq":
        pages_dir = vault / "pages"
        if pages_dir.exists():
            for path in pages_dir.glob("*.md"):
                titles.append(path.stem)
    else:
        if vault.exists():
            for path in vault.rglob("*.md"):
                if path.parent.name == "Inbox":
                    continue
                titles.append(path.stem)

    _cached_titles = sorted(titles)
    _last_fetch = now
    logger.debug("Indexed %d vault titles", len(_cached_titles))
    return _cached_titles
```

- [ ] **Step 4: Update existing test patches**

In `tests/test_vault_index.py`, update patches:

```python
def test_get_titles_collects_md_files():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "Note One.md").write_text("x")
        (Path(tmp) / "Note Two.md").write_text("y")
        (Path(tmp) / "Inbox").mkdir()
        (Path(tmp) / "Inbox" / "Draft.md").write_text("z")
        with patch("src.vault_index.settings.VAULT_BACKEND", "obsidian"), \
             patch("src.vault_index.settings.VAULT_PATH", tmp):
            clear_cache()
            titles = get_titles()
            assert "Note One" in titles
            assert "Note Two" in titles
            assert "Draft" not in titles


def test_get_titles_uses_cache():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "A.md").write_text("x")
        with patch("src.vault_index.settings.VAULT_BACKEND", "obsidian"), \
             patch("src.vault_index.settings.VAULT_PATH", tmp):
            clear_cache()
            first = get_titles()
            (Path(tmp) / "A.md").unlink()
            second = get_titles()
            assert first == second
            assert "A" in second
```

- [ ] **Step 5: Run all vault index tests**

Run: `pytest tests/test_vault_index.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/vault_index.py tests/test_vault_index.py
git commit -m "feat: vault index branches on VAULT_BACKEND for Obsidian/Logseq"
```

---

### Task 6: Bot updates

**Files:**

- Modify: `src/bot.py:22,39,55`

- [ ] **Step 1: Update bot.py**

Replace line 22:
```python
INBOX_PREFIX = "Inbox/"
```
with nothing (delete the line).

Replace line 39:
```python
        f"📄 Saved to <code>{INBOX_PREFIX}{filename}</code>",
```
with:
```python
        f"📄 Saved to <code>{filename}</code>",
```

Replace line 55:
```python
    "Send me a URL and I'll summarise it into a structured Obsidian note.\n\n"
```
with:
```python
    "Send me a URL and I'll summarise it into a structured note.\n\n"
```

- [ ] **Step 2: Run bot tests**

Run: `pytest tests/test_bot.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/bot.py
git commit -m "fix: remove Obsidian-specific INBOX_PREFIX from bot confirmation"
```

---

### Task 7: Update integration tests

**Files:**

- Modify: `tests/test_integration.py:11,16,35-36,59-60`

- [ ] **Step 1: Update imports and patches**

Replace `ObsidianMetadata` with `VaultMetadata` on lines 11 and 16.

Replace `OBSIDIAN_VAULT_PATH` patches with `VAULT_PATH` + `VAULT_BACKEND` on lines 35-36:
```python
        with patch("src.vault.settings.VAULT_BACKEND", "obsidian"), \
             patch("src.vault.settings.VAULT_PATH", tmp), \
             patch("src.vault_index.settings.VAULT_BACKEND", "obsidian"), \
             patch("src.vault_index.settings.VAULT_PATH", tmp):
```

Same pattern for lines 59-60.

The dry-run assertion (lines 73-74) already correctly checks `Inbox/` for the Obsidian backend path — no change needed there:
```python
                    inbox = Path(tmp) / "Inbox"
                    assert not inbox.exists() or not any(inbox.iterdir())
```

- [ ] **Step 2: Add Logseq dry-run integration test**

Add a new test after `test_pipeline_dry_run_does_not_write`:

```python
@pytest.mark.asyncio
async def test_pipeline_dry_run_logseq_does_not_write():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("src.vault.settings.VAULT_BACKEND", "logseq"), \
             patch("src.vault.settings.VAULT_PATH", tmp), \
             patch("src.vault_index.settings.VAULT_BACKEND", "logseq"), \
             patch("src.vault_index.settings.VAULT_PATH", tmp):
            with patch("src.main.fetch", new_callable=AsyncMock) as mock_fetch, \
                 patch("src.main.classify", new_callable=AsyncMock) as mock_classify, \
                 patch("src.main.summarise", new_callable=AsyncMock) as mock_summarise:
                mock_fetch.return_value = ("Article text", None)
                mock_classify.return_value = ContentType.article
                mock_summarise.return_value = _article_fixture()

                path, note = await run_pipeline(
                    "https://example.com/article", dry_run=True
                )

                assert path is None
                pages = Path(tmp) / "pages"
                assert not pages.exists() or not any(pages.iterdir())
```

- [ ] **Step 3: Run integration tests**

Run: `pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: update integration tests for VaultPath, VaultMetadata, and Logseq backend"
```

---

### Task 8: Infrastructure files

**Files:**

- Modify: `docker-compose.yml:31-33`
- Modify: `.env.example:35-38`

- [ ] **Step 1: Update docker-compose.yml**

Replace lines 30-33:
```yaml
      # ── Vault ────────────────────────────────────────────────────────
      - OBSIDIAN_VAULT_PATH=${OBSIDIAN_VAULT_PATH:-/tmp/chickadee-vault}
      - OBSIDIAN_API_KEY=${OBSIDIAN_API_KEY:-}
      - OBSIDIAN_BASE_URL=${OBSIDIAN_BASE_URL:-}
```
with:
```yaml
      # ── Vault ────────────────────────────────────────────────────────
      - VAULT_BACKEND=${VAULT_BACKEND:-obsidian}
      - VAULT_PATH=${VAULT_PATH:-/tmp/chickadee-vault}
```

- [ ] **Step 2: Update .env.example**

Replace lines 35-38:
```
# ── Vault ──────────────────────────────────────────────────────────────
OBSIDIAN_VAULT_PATH=/tmp/chickadee-vault
OBSIDIAN_API_KEY=
OBSIDIAN_BASE_URL=
```
with:
```
# ── Vault ──────────────────────────────────────────────────────────────
VAULT_BACKEND=obsidian              # or logseq
VAULT_PATH=/tmp/chickadee-vault
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "chore: rename vault env vars, remove unused OBSIDIAN_* API vars"
```

---

### Task 9: ADR

**Files:**

- Create: `docs/adr/0001-logseq-vault-backend.md`

- [ ] **Step 1: Create ADR**

```markdown
# Logseq vault backend

Chickadee supports two vault backends — Obsidian (YAML frontmatter, `Inbox/` directory) and Logseq (`property:: value` syntax, `pages/` directory). Selected via `VAULT_BACKEND` env var. Default is Obsidian for backward compatibility.

The vault layer is thin (~250 lines across 3 files) and the only difference is metadata format. LLM prompts, agent logic, body rendering, and all other pipeline code is backend-agnostic. A single codebase with conditional rendering is simpler than maintaining two forks.

ObsidianMetadata was renamed to VaultMetadata to reflect backend independence.
```

- [ ] **Step 2: Commit**

```bash
mkdir -p docs/adr
git add docs/adr/
git commit -m "docs: add ADR for Logseq vault backend decision"
```

---

### Task 9.5: Update documentation files

**Files:**

- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `DESIGN.md`

- [ ] **Step 1: Update AGENTS.md**

Replace `ObsidianMetadata` → `VaultMetadata` (line 49).

Update the Vault integration section (lines 217-230):
- Remove "Option A" REST API section entirely (lines 219-223)
- Replace `OBSIDIAN_VAULT_PATH` with `VAULT_PATH` (line 225)
- Add note about Logseq backend: `Write to {vault_path}/{Inbox or pages}/{slug}.md depending on VAULT_BACKEND`
- Update the env vars section (lines 310-312): replace `OBSIDIAN_VAULT_PATH`, `OBSIDIAN_API_KEY`, `OBSIDIAN_BASE_URL` with `VAULT_BACKEND=obsidian` (or `logseq`) and `VAULT_PATH`

Update the Renderer section (line 156): `"Obsidian-compatible"` → `"Obsidian or Logseq"`.

Update the What this app does section (lines 5-7): `"YAML frontmatter"` → `"YAML frontmatter or Logseq properties"`, `"Obsidian vault"` → `"knowledge vault"`.

- [ ] **Step 2: Update README.md**

Replace:
- Line 3: `"Obsidian vault"` → `"knowledge vault"`
- Line 46: `export OBSIDIAN_VAULT_PATH="/app/vault"` → `export VAULT_PATH="/app/vault"`, add `export VAULT_BACKEND=obsidian` line above it
- Line 72: Keep `mkdir -p .../vault/Inbox` but add a comment about Logseq's `pages/` alternative

- [ ] **Step 3: Update DESIGN.md**

Replace:
- Line 23: `"filed into Obsidian"` → `"filed into vault (Obsidian or Logseq)"`
- Line 49: `OBSIDIAN_VAULT_PATH` → `VAULT_PATH`
- Epics 6-7 descriptions: lightly update to reflect backend-agnostic language
- Backlog section lines 241-244: Remove "Obsidian REST API mode" entry (its env vars are being removed)

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md README.md DESIGN.md
git commit -m "docs: update for dual-backend vault (Obsidian + Logseq)"
```

---

### Task 10: Final verification

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: Dry run with Obsidian backend**

Run: `VAULT_BACKEND=obsidian python -m src.main https://example.com --dry-run`
Expected: Output starts with `---\ntags:` YAML frontmatter

- [ ] **Step 3: Dry run with Logseq backend**

Run: `VAULT_BACKEND=logseq python -m src.main https://example.com --dry-run`
Expected: Output starts with `tags::` property syntax, no `---` delimiters

- [ ] **Step 4: Verify no regressions**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass, no import errors

---

### Task 11: Logseq web app Docker setup

**Files:**

- Modify: `docker-compose.yml`
- Create: `nginx/logseq-ssl.conf` (if using HTTPS)

**Important caveats before proceeding:**

The Logseq web app (`ghcr.io/logseq/logseq-webapp`) uses the browser's [File System Access API](https://developer.mozilla.org/en-US/docs/Web/API/File_System_Access_API) to read/write the graph directory. This means:

1. **HTTPS required for remote access** — the API is blocked over plain HTTP on non-localhost origins
2. **Manual graph selection** — each time you open the web app, you must click "Open graph" and select the vault directory in the browser. There is no way to auto-load a graph via URL parameter
3. **Browser-only** — this is a web UI, not a server-side app. You interact with it through a browser on another device

This is the official Docker deployment path. It works, but it's not a "set and forget" server like Chickadee. You'll interact with it through a browser.

- [ ] **Step 1: Add Logseq service to docker-compose.yml**

Add a `logseq` service alongside `chickadee`:

```yaml
  logseq:
    image: ghcr.io/logseq/logseq-webapp:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:3001:80"
    volumes:
      - ${VAULT_PATH:-/tmp/chickadee-vault}:/graphs/chickadee
```

Note: The vault bind mount path uses `VAULT_PATH` to match the config from Task 1. Logseq will see the `pages/` directory inside `/graphs/chickadee/`.

- [ ] **Step 2: Test local access**

```bash
docker compose up -d logseq
```

Open browser to `http://localhost:3001`. Click "Open graph" → select `/graphs/chickadee`. Notes should appear.

- [ ] **Step 3: Set up HTTPS for remote access**

For accessing from other devices (phone, laptop), HTTPS is required. Generate a self-signed cert:

```bash
# Install mkcert (macOS)
brew install mkcert

# Install local CA
mkcert -install

# Generate cert for server IP
mkcert 192.168.1.100  # replace with your server IP
```

Copy the `.pem` and `-key.pem` files to the server.

- [ ] **Step 4: Add nginx reverse proxy with SSL**

Create `nginx/logseq-ssl.conf`:

```nginx
server {
    listen 443 ssl;
    ssl_certificate /etc/nginx/certs/logseq.pem;
    ssl_certificate_key /etc/nginx/certs/logseq-key.pem;

    location / {
        proxy_pass http://logseq:80;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

Add nginx to `docker-compose.yml`:

```yaml
  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "443:443"
    volumes:
      - ./nginx/logseq-ssl.conf:/etc/nginx/conf.d/logseq-ssl.conf
      - ./certs:/etc/nginx/certs
    depends_on:
      - logseq
```

- [ ] **Step 5: Test remote access**

Open browser on another device: `https://192.168.1.100` (accept self-signed cert warning). Click "Open graph" → navigate to `/graphs/chickadee`.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml nginx/
git commit -m "feat: add Logseq web app with HTTPS for remote access"
```

---

### Logseq limitations (known issues)

| Issue | Impact | Workaround |
|-------|--------|------------|
| Manual graph selection each session | Must click "Open graph" every time you open the web app | No workaround — this is how the File System Access API works |
| HTTPS required for remote access | Can't use plain HTTP from phone/laptop | mkcert for self-signed certs, or Let's Encrypt for public domains |
| No multi-user support | Single user graph only | Fine for personal use |
| File-based graph (not DB) | No real-time sync between browser tabs | Close and reopen graph to see new notes from Chickadee |
| Web app only (no mobile app) | No native iOS/Android app for self-hosted | Use PWA or browser bookmark |

**Alternative if these limitations are a dealbreaker:** Install Logseq Desktop on your MacBook and point it at the vault via NFS/SMB mount. This gives you the full desktop experience with no HTTPS requirement and auto-loads the graph.

---

### Task 12: Obsidian Docker setup (alternative to Logseq)

**Files:**

- Modify: `docker-compose.yml`

For users who prefer Obsidian over Logseq, the `lscr.io/linuxserver/obsidian` image runs a full desktop Obsidian instance in the container, accessible via browser. This is heavier than Logseq but gives you the full Obsidian experience with plugins, graph view, and themes.

- [ ] **Step 1: Add Obsidian service to docker-compose.yml**

Add an `obsidian` service (alternative to `logseq` — user picks one):

```yaml
  obsidian:
    image: lscr.io/linuxserver/obsidian:latest
    container_name: chickadee-obsidian
    restart: unless-stopped
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Etc/UTC
    volumes:
      - ${VAULT_PATH:-/tmp/chickadee-vault}:/config/Obsidian
      - ./obsidian-config:/config
    ports:
      - "3001:3001"
    shm_size: "1gb"
```

The vault is mounted at `/config/Obsidian` inside the container. Open Obsidian in the container's desktop and select the `Obsidian` folder as the vault.

- [ ] **Step 2: Test access**

```bash
docker compose up -d obsidian
```

Open browser to `https://localhost:3001` (self-signed cert). In the Obsidian desktop, File → Open vault → select the `Obsidian` folder. Notes from Chickadee should appear.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add Obsidian Docker option via linuxserver/obsidian"
```

---

### Self-hosting comparison: Logseq vs Obsidian

| | Logseq Web App | Obsidian (linuxserver) |
|---|---|---|
| **Image** | `ghcr.io/logseq/logseq-webapp` | `lscr.io/linuxserver/obsidian` |
| **Weight** | Light (static web app) | Heavy (full Linux desktop) |
| **RAM** | ~100MB | ~1GB (shm_size) |
| **Plugins** | Limited | Full Obsidian ecosystem |
| **Graph view** | Basic | Full |
| **Mobile access** | Browser only | Browser (VNC-style) |
| **Auto-loads vault** | No (manual selection) | No (manual selection) |
| **HTTPS** | Required for remote | Self-signed included |
| **Best for** | Lightweight, minimal VPS | Full Obsidian experience |

**Both require the user to select the vault directory in the browser on first load.** There is no way to auto-load a vault via URL parameter in either solution.

**Cheapest VPS recommendation:** 2 vCPU, 2GB RAM. Enough for Chickadee + Logseq. For Obsidian, 2GB RAM minimum (the desktop is heavier).
