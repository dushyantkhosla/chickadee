# DONE

- Project scaffold — pyproject.toml, config, models, exceptions
- Fetcher — async HTML + YouTube transcript extraction
- Router — domain-based ContentType routing
- Classifier — LLM content type fallback for ambiguous URLs
- Summariser — PydanticAI agent producing typed *Note objects
- Renderer — AnyNote → Obsidian Markdown with YAML frontmatter
- Vault writer — filesystem write to Inbox/ with slugged filenames
- Vault index — cached .md title scanner with Inbox exclusion
- Integration pipeline — fetch → route → classify → index → summarise → render → write
- CLI — `--dry-run` flag, error handling at every stage
- Telegram bot — polling mode, URL → note flow with confirmation messages
