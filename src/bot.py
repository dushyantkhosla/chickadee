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
