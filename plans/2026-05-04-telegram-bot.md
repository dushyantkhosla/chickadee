# Telegram Bot — Spec & Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A minimal Telegram bot that receives a URL, runs the existing chickadee pipeline, and replies with a confirmation containing the note title, tags, and a one-line summary.

**Architecture:** Single `src/bot.py` module with a `ChickadeeBot` class wrapping PTB `Application` in polling mode. Reuses `src.main.run_pipeline` with a minor return-type change. No interactive forms, no sessions, no keyboards.

**Tech Stack:** `python-telegram-bot` v21+, existing chickadee pipeline (PydanticAI, LM Studio, Obsidian vault)

---

## Spec

### Interaction model

User sends a message containing a URL → bot validates auth → starts typing indicator → runs `fetch → route/classify → summarise → render → write` → replies with:

```
✅ <b>{title}</b>
🏷️  <code>tag1</code> <code>tag2</code> <code>tag3</code>
📝 {thesis or what_changed, first 200 chars}
📄 Saved to Inbox/{filename}
```

Non-URL messages → help text. Commands `/start`, `/help` → help text. Busy indicator if a previous request is still processing.

### Error handling

Stage-specific failure message:

```
❌ <b>Chickadee — FetchError</b>
Could not fetch the URL.
URL: https://...
```

Error types: `FetchError`, `ParseError`, `VaultWriteError`, generic `Exception`.

### Auth

`BOT_ALLOWED_CHAT_IDS` env var — comma-separated list of numeric chat IDs, or `*` for open access. If `*` is present, all chat IDs are allowed.

### Files

| File | Action | Purpose |
|---|---|---|
| `pyproject.toml` | Edit | Add `python-telegram-bot>=21` dependency |
| `src/config.py` | Edit | Add `BOT_ALLOWED_CHAT_IDS: str = "*"` field |
| `src/main.py` | Edit | `run_pipeline()` returns `tuple[Path | None, AnyNote]` so bot can display note info |
| `src/bot.py` | Create | `ChickadeeBot` class + `__main__` entrypoint |
| `tests/test_bot.py` | Create | Tests for bot message formatting + config |

---

## Plan

### Task 1: Add dependency and config

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/config.py`

- [ ] **Step 1: Add `python-telegram-bot` to dependencies**

Edit `pyproject.toml` to add the dependency:

```toml
dependencies = [
    "pydantic-ai-slim[openai]>=1.89.1",
    "httpx>=0.28",
    "trafilatura>=2.0",
    "youtube-transcript-api>=1.0",
    "pydantic-settings>=2.0",
    "python-dotenv>=1.0",
    "python-slugify>=8.0",
    "pyyaml>=6.0",
    "python-telegram-bot>=21",
]
```

- [ ] **Step 2: Add `BOT_ALLOWED_CHAT_IDS` to config**

Insert after `TELEGRAM_WEBHOOK_SECRET` in `src/config.py`:

```python
    BOT_ALLOWED_CHAT_IDS: str = "*"
```

- [ ] **Step 3: Verify config loads cleanly**

Run: `cd /Users/dush/Code/2026/chickadee && python -c "from src.config import settings; print(settings.BOT_ALLOWED_CHAT_IDS)"`
Expected: `*`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/config.py
git commit -m "feat: add telegram-bot dependency and config"
```

---

### Task 2: Modify `run_pipeline` to return note alongside path

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Update `run_pipeline` signature and return type**

Change `run_pipeline` to return a tuple `(Path | None, AnyNote)` instead of `Path | None`.

Add `AnyNote` to the imports from `src.models`:

```python
from src.models import AnyNote, ContentType, note_to_slug
```

Update the return statement to include the note:

```python
async def run_pipeline(url: str, dry_run: bool = False) -> tuple[Path | None, AnyNote]:
    """Full pipeline: fetch → route/classify → index → summarise → render → write.
    
    Returns (path, note). path is None when dry_run=True.
    """
    print(f"Fetching {url} ...")
    text = await fetch(url)
    print(f"Fetched {len(text.split())} words")

    content_type = await resolve_content_type(url, text)
    print(f"Resolved type: {content_type.value}")

    vault_titles = get_titles()
    print(f"Vault index: {len(vault_titles)} titles")

    note = await summarise(text, content_type, vault_titles, url)
    title = getattr(note, "title", getattr(note, "name", "untitled"))
    print(f"Summarised: {title}")

    markdown = render(note)
    print(f"Rendered {len(markdown)} chars")

    if dry_run:
        print("\n--- DRY RUN ---\n")
        print(markdown)
        return None, note

    filename = make_filename(note_to_slug(note))
    path = write(filename, markdown)
    print(f"Written to {path}")
    return path, note
```

Update `main()` to unpack the tuple:

```python
def main() -> None:
    parser = argparse.ArgumentParser(description="Chickadee — structured summarisation")
    parser.add_argument("url", help="URL to summarise")
    parser.add_argument("--dry-run", action="store_true", help="Render without writing")
    args = parser.parse_args()

    try:
        path, note = asyncio.run(run_pipeline(args.url, dry_run=args.dry_run))
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 2: Run existing tests to verify nothing broke**

Run: `cd /Users/dush/Code/2026/chickadee && .venv/bin/pytest -v`
Expected: All 58 tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "refactor: run_pipeline returns (path, note) tuple for bot integration"
```

---

### Task 3: Write the bot module

**Files:**
- Create: `src/bot.py`
- Test: `tests/test_bot.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_bot.py`:

```python
"""Tests for Telegram bot — formatting and config."""

import pytest
from src.config import settings
from src.bot import format_confirmation, format_error


def test_config_has_bot_fields():
    """Config loads telegram-related env vars."""
    # These should exist without crashing
    assert hasattr(settings, "TELEGRAM_BOT_TOKEN")
    assert hasattr(settings, "BOT_ALLOWED_CHAT_IDS")


def test_format_confirmation_article():
    """ArticleNote produces a formatted confirmation message."""
    from datetime import date
    from src.models import ArticleNote, ObsidianMetadata, ContentType

    note = ArticleNote(
        meta=ObsidianMetadata(
            tags=["python", "testing"],
            source_url="https://example.com/article",
            source_type=ContentType.article,
            ingested_on=date.today(),
        ),
        title="Test Article",
        thesis="This is a test article about testing things thoroughly.",
        key_points=["Point one"],
        evidence=["Evidence one"],
    )
    msg = format_confirmation(note, "2026-05-04_test-article.md")
    assert "✅" in msg
    assert "Test Article" in msg
    assert "python" in msg
    assert "testing things thoroughly" in msg
    assert "test-article.md" in msg


def test_format_confirmation_repo():
    """RepoNote uses 'name' instead of 'title'."""
    from datetime import date
    from src.models import RepoNote, ObsidianMetadata, ContentType

    note = RepoNote(
        meta=ObsidianMetadata(
            tags=["tooling"],
            source_url="https://github.com/example/repo",
            source_type=ContentType.repo,
            ingested_on=date.today(),
        ),
        name="chickadee",
        what_it_does="A summarisation pipeline",
        stack=["Python"],
        key_patterns=["Agent pattern"],
    )
    msg = format_confirmation(note, "2026-05-04_chickadee.md")
    assert "chickadee" in msg
    assert "tooling" in msg


def test_format_error():
    """Error message includes error type and URL."""
    msg = format_error("FetchError", "Could not fetch", "https://example.com")
    assert "FetchError" in msg
    assert "Could not fetch" in msg
    assert "https://example.com" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/dush/Code/2026/chickadee && .venv/bin/pytest tests/test_bot.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.bot'" (or import errors)

- [ ] **Step 3: Write the bot module**

Create `src/bot.py`:

```python
"""Chickadee Telegram bot — polling mode, single URL → note flow."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from telegram import MessageEntity, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from src.config import settings
from src.main import run_pipeline

if TYPE_CHECKING:
    from src.models import AnyNote

logger = logging.getLogger(__name__)

INBOX_PREFIX = "Inbox/"


def format_confirmation(note: AnyNote, filename: str) -> str:
    """Build a Telegram HTML message confirming a note was created."""
    title = getattr(note, "title", None) or getattr(note, "name", "untitled")
    tags = " ".join(f"<code>{t}</code>" for t in note.meta.tags[:5])
    # Extract one-line summary from thesis or what_changed
    summary = getattr(note, "thesis", None) or getattr(note, "what_changed", "")
    if summary:
        summary = summary[:200]
        if len(summary) == 200:
            summary += "…"
    lines = [
        f"✅ <b>{title}</b>",
        f"🏷️  {tags}",
        f"📝 {summary}",
        f"📄 Saved to <code>{INBOX_PREFIX}{filename}</code>",
    ]
    return "\n".join(lines)


def format_error(error_type: str, message: str, url: str) -> str:
    """Build a Telegram HTML message for a pipeline failure."""
    return (
        f"❌ <b>Chickadee — {error_type}</b>\n"
        f"{message}\n"
        f"URL: {url}"
    )


HELP_TEXT = (
    "🤖 <b>Chickadee</b>\n\n"
    "Send me a URL and I'll summarise it into a structured Obsidian note.\n\n"
    "Works with: articles, YouTube talks, papers, essays, GitHub repos, field reports."
)


class ChickadeeBot:
    """Minimal Telegram bot: receives URL, runs pipeline, replies with confirmation."""

    def __init__(self, token: str, allowed_chat_ids: set[int | str]) -> None:
        if "*" in allowed_chat_ids:
            allowed_chat_ids = {"*"}
        self._allowed = allowed_chat_ids
        self._active: set[int] = set()
        self._typing_tasks: dict[int, asyncio.Task] = {}
        self._app = Application.builder().token(token).build()

        self._app.add_handler(CommandHandler("start", self._cmd_help))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & filters.Entity(MessageEntity.URL),
                self._handle_url,
            )
        )
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._cmd_help)
        )

    def _is_allowed(self, chat_id: int) -> bool:
        return self._allowed == {"*"} or chat_id in self._allowed

    async def start(self) -> None:
        """Start polling."""
        await self._app.initialize()
        await self._app.bot.set_my_commands([])
        await self._app.start()
        await self._app.updater.start_polling()
        logger.info("Bot started (polling mode)")

    async def stop(self) -> None:
        """Stop polling and cancel pending typing tasks."""
        for task in self._typing_tasks.values():
            if not task.done():
                task.cancel()
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def _cmd_help(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._is_allowed(update.effective_chat.id):
            return
        await update.message.reply_text(HELP_TEXT, parse_mode="HTML")

    async def _handle_url(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat_id = update.effective_chat.id
        if not self._is_allowed(chat_id):
            return
        if chat_id in self._active:
            await update.message.reply_text(
                "⏳ Still processing your previous request, please wait."
            )
            return

        # Extract the first URL from the message
        entities = update.message.parse_entities([MessageEntity.URL])
        if not entities:
            return
        url = next(iter(entities.values()))

        self._active.add(chat_id)
        self._start_typing(chat_id)

        try:
            path, note = await run_pipeline(url)
            filename = path.name if path else "unknown"
            msg = format_confirmation(note, filename)
            await update.message.reply_text(msg, parse_mode="HTML")
        except Exception as exc:
            error_type = type(exc).__name__
            await update.message.reply_text(
                format_error(error_type, str(exc), url),
                parse_mode="HTML",
            )
        finally:
            self._stop_typing(chat_id)
            self._active.discard(chat_id)

    def _start_typing(self, chat_id: int) -> None:
        self._stop_typing(chat_id)

        async def typing_loop():
            try:
                while True:
                    await self._app.bot.send_chat_action(
                        chat_id=chat_id, action=ChatAction.TYPING
                    )
                    await asyncio.sleep(4)
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        self._typing_tasks[chat_id] = asyncio.create_task(typing_loop())

    def _stop_typing(self, chat_id: int) -> None:
        task = self._typing_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()


# ── CLI entrypoint ──────────────────────────────────────────────────────────


def _parse_allowed(raw: str) -> set[int | str]:
    """Parse comma-separated chat IDs or '*' for open access."""
    if raw.strip() == "*":
        return {"*"}
    return {int(x.strip()) for x in raw.split(",") if x.strip()}


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    token = settings.TELEGRAM_BOT_TOKEN
    allowed = _parse_allowed(settings.BOT_ALLOWED_CHAT_IDS)
    bot = ChickadeeBot(token, allowed)

    async def run():
        await bot.start()
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            await bot.stop()

    asyncio.run(run())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/dush/Code/2026/chickadee && .venv/bin/pytest tests/test_bot.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/bot.py tests/test_bot.py
git commit -m "feat: add Telegram bot module (polling mode, URL→note flow)"
```

---

### Task 4: Update `.env.example` and verify full test suite

**Files:**
- Modify: `.env` (if exists as example)
- Check: `.gitignore`

- [ ] **Step 1: Ensure `TELEGRAM_BOT_TOKEN` is documented**

Check `.env` has the token field:

```bash
grep -q "TELEGRAM_BOT_TOKEN" .env || echo "TELEGRAM_BOT_TOKEN=" >> .env
```

- [ ] **Step 2: Run full test suite**

Run: `cd /Users/dush/Code/2026/chickadee && .venv/bin/pytest -v`
Expected: 62 tests pass (58 existing + 4 new)

- [ ] **Step 3: Commit**

```bash
git add .env
git commit -m "chore: add TELEGRAM_BOT_TOKEN placeholder to .env"
```
