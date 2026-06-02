# AGENTS.md — Chickadee

## What this app does

Telegram bot receives a URL → PydanticAI agent fetches and reads the content →
produces a typed `*Note` object → renders it as Markdown with YAML frontmatter →
writes it to the Obsidian vault.

One human action (send link). Everything else is automated.

---

## Project layout

```
.
├── AGENTS.md                 # this file
├── src/
│   ├── models.py             # Pydantic note types — source of truth for all schemas
│   ├── router.py             # URL → ContentType detection
│   ├── fetcher.py            # URL → text (yt-dlp for YouTube, httpx+trafilatura for web)
│   ├── transcriber.py        # yt-dlp audio download + OpenRouter transcription
│   ├── agent.py              # PydanticAI agents: classify + summarise
│   ├── renderer.py           # AnyNote → Markdown string
│   ├── vault.py              # Write to Obsidian (filesystem)
│   ├── vault_index.py        # Reads vault note titles for link grounding
│   ├── bot.py                # Telegram bot (polling mode)
│   ├── config.py             # Pydantic settings from .env
│   ├── exceptions.py         # FetchError, ParseError, VaultWriteError
│   └── lmstudio_utils.py     # LM Studio server + model management (CLI)
├── tests/
├── plans/
└── pyproject.toml
```

---

## Models (models.py)

`models.py` is the single source of truth. Do not duplicate field definitions elsewhere.

Six note types, all sharing two embedded models:

- `ObsidianMetadata` — vault housekeeping: tags, link fields, source, date, upload_date
- `Reflection` — personal interpretation: `my_take`, `so_what`, `now_what`

Every note type also has `open_questions: list[str]`.

| Type | Routed from | Key distinguishing fields |
|---|---|---|
| `TalkNote` | youtube.com, vimeo.com | `speaker` (from yt-dlp channel), `thesis`, `arguments`, `key_quotes` |
| `ArticleNote` | general web | `thesis`, `key_points`, `evidence` |
| `PaperNote` | arxiv.org, doi.org | `hypothesis`, `methodology`, `findings`, `limitations` |
| `EssayNote` | substack.com, opinion sites | `claimed` vs `evidenced` (separated deliberately) |
| `RepoNote` | github.com | `what_it_does`, `stack`, `key_patterns` |
| `FieldNote` | simonwillison.net, practitioner blogs | `what_changed`, `data_points`, `code_snippets`, `authors_take`, `shelf_life` |

Union type: `AnyNote = TalkNote | ArticleNote | PaperNote | EssayNote | RepoNote | FieldNote`

Routing constants `UNAMBIGUOUS_DOMAINS` (dict) and `MULTI_TYPE_DOMAINS` (set) live at the bottom of `models.py`.

---

## Agent behaviour (agent.py)

### Routing

Two-tier strategy — domain alone is not always sufficient:

**Tier 1 — Unambiguous domains** (`UNAMBIGUOUS_DOMAINS` in `models.py`)
Domain determines `ContentType` with certainty. Skip LLM classification entirely.
Examples: `youtube.com` → `TalkNote`, `arxiv.org` → `PaperNote`, `github.com` → `RepoNote`.

**Tier 2 — Everything else** (unknown domains + `MULTI_TYPE_DOMAINS`)
Fetch the article first, then run a cheap LLM classification call to determine
`ContentType` before the main summarisation call. `MULTI_TYPE_DOMAINS` documents
known multi-type domains (e.g. `anthropic.com`, `simonwillison.net`) as a guard
against accidentally adding them to the unambiguous whitelist.

Classification and summarisation must be **two separate LLM calls** — doing both
in one pass causes the model to anchor on the wrong type early.

**Decision tree:**
```
domain in UNAMBIGUOUS_DOMAINS → type decided, proceed to summarisation
         ↓
fetch content (YouTube: yt-dlp → OpenRouter transcription; web: httpx + trafilatura)
         ↓
LLM classifies ContentType (6 options, enum-constrained)
         ↓
LLM summarises into matched schema
```

Default fallback if classification is uncertain: `ContentType.article`.

### YouTube flow

For YouTube URLs, metadata (title, channel, categories, upload_date) comes from yt-dlp — the LLM only produces summary content (thesis, arguments, quotes, etc.) via PydanticAI `deps_type` (`TalkMetadata`).

### Link grounding

- Before calling the LLM, read the vault index (note titles only)
- Pass titles as a list in the system prompt
- Instruct: *populate `builds_on`, `see_also`, `contradicts` using exact titles from this list only — leave empty if no confident match*
- Never allow the LLM to invent note titles

### Prompting principles

- Always pass the resolved `ContentType` explicitly into the summarisation call — never ask the summarisation model to infer it
- For `Reflection`: instruct the model to leave fields `None` rather than pad with generic text
- For `FieldNote.authors_take`: instruct the model to distinguish the author's opinion from reported facts
- For `PaperNote`: follow IMRaD — hypothesis → methodology → findings → limitations
- For `EssayNote`: actively separate `claimed` (opinion/intuition) from `evidenced` (data/citations)

---

## Renderer (renderer.py)

Converts any `*Note` to an Obsidian-compatible `.md` file.

### Frontmatter

```yaml
---
tags: [tag-one, tag-two]
builds_on: ["[[Note Title A]]", "[[Note Title B]]"]
see_also: ["[[Note Title C]]"]
contradicts: []
source_url: https://...
source_type: talk
ingested_on: 2026-06-02
upload_date: 2026-04-24          # optional, from source
---
```

Link fields wrap each title in `[[...]]` — Obsidian wikilink syntax.
Empty lists render as `[]` — do not omit them.

### Body structure (all types)

```markdown
# {title}

_{author or speaker if present}_

## Summary
{thesis or what_changed — the one-sentence anchor}

## {Type-specific section}
{arguments / key_points / findings / etc.}

## Open questions
- ...

## Reflection
**My take:** ...
**So what:** ...
**Now what:** ...
```

For `FieldNote`, add:

```markdown
## Data points
- ...

## Code
\`\`\`bash
...
\`\`\`

**Author's take:** ...
**Shelf life:** months
```

---

## Vault integration (vault.py)

Two modes — pick one at setup, configure via `.env`:

**Option A — Obsidian Local REST API** (community plugin required)
- Plugin: `obsidian-local-rest-api`
- Endpoint: `PUT /vault/{filename}`
- Set `OBSIDIAN_API_KEY` and `OBSIDIAN_BASE_URL` in `.env`

**Option B — Direct filesystem write**
- Set `OBSIDIAN_VAULT_PATH` in `.env`
- Write to `{vault_path}/Inbox/{slug}.md`
- Simpler if the vault is on the same machine or a mounted network drive

File naming: `{YYYY-MM-DD}_{slugified-title}.md`
Target folder: `Inbox/` — let Obsidian's graph form naturally, move notes manually later.

---

## Telegram bot (bot.py)

- Single command: user sends a URL
- Bot replies immediately: "Received. Filing it away now..."
- Processing happens in background (async deque per chat)
- Bot replies on completion: note title + tags + summary
- Bot replies on failure: error type + URL
- User can paste another URL while processing — no blocking

---

## LM Studio (lmstudio_utils.py)

CLI-based helpers for `lms` CLI:
- `ensure_server_running()` — starts server if not running
- `load_model(name, ttl=900)` — loads with TTL for auto-unload
- `unload_model(name)` — frees GPU memory
- `is_model_loaded(name)` — checks `lms ps`
- `ensure_model_loaded(name)` — convenience: server + load

The pipeline unloads the model in a `finally` block after each run. Retry-on-unload logic exists in `classify()` and `summarise()` (up to 3 attempts).

---

## Environment variables (.env)

```
OPENROUTER_API_KEY=             # YouTube transcription (OpenRouter mimo-v2.5)
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
BOT_ALLOWED_CHAT_IDS=*          # comma-separated or * for open access

LM_STUDIO_BASE_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=local-model

# Vault — choose one mode
OBSIDIAN_VAULT_PATH=            # Option B: filesystem path
OBSIDIAN_API_KEY=               # Option A: REST API key
OBSIDIAN_BASE_URL=              # Option A: e.g. http://localhost:27123
```

---

## Constraints and preferences

- Pseudocode before implementation on anything non-trivial
- No placeholder text in `Reflection` fields — `None` is correct when uncertain
- `models.py` is append-only for new note types — never modify existing field names once the vault has notes using them (breaks frontmatter parsing)
- Keep `UNAMBIGUOUS_DOMAINS` updated as new domains are added
- Run `pytest` before committing — 71 tests must pass
