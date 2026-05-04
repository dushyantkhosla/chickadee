# CLAUDE.md — Structured Summarisation Pipeline

## What this app does

Telegram bot receives a URL → PydanticAI agent fetches and reads the content →
produces a typed `*Note` object → renders it as Markdown with YAML frontmatter →
writes it to the Obsidian vault.

One human action (send link). Everything else is automated.

---

## Project layout

```
.
├── CLAUDE.md               # this file
├── models.py               # Pydantic note types — source of truth for all schemas
├── router.py               # URL → ContentType detection
├── agent.py                # PydanticAI agent: fetch + summarise + structure
├── renderer.py             # AnyNote → Markdown string
├── vault.py                # Write to Obsidian (REST API or filesystem)
├── bot.py                  # Telegram webhook handler
├── vault_index.py          # Reads vault note titles for link grounding
└── .env                    # secrets — never commit
```

---

## Models (models.py)

`models.py` is the single source of truth. Do not duplicate field definitions elsewhere.

Six note types, all sharing two embedded models:

- `ObsidianMetadata` — vault housekeeping: tags, link fields, source, date
- `Reflection` — personal interpretation: `my_take`, `so_what`, `now_what`

Every note type also has `open_questions: list[str]`.

| Type | Routed from | Key distinguishing fields |
|---|---|---|
| `TalkNote` | youtube.com, vimeo.com | `speaker`, `thesis`, `arguments`, `key_quotes` |
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
Fetch the article first, then run a cheap LLM classification call (Haiku) to determine
`ContentType` before the main summarisation call. `MULTI_TYPE_DOMAINS` documents
known multi-type domains (e.g. `anthropic.com`, `simonwillison.net`) as a guard
against accidentally adding them to the unambiguous whitelist.

Classification and summarisation must be **two separate LLM calls** — doing both
in one pass causes the model to anchor on the wrong type early.

**Decision tree:**
```
domain in UNAMBIGUOUS_DOMAINS → type decided, proceed to summarisation
         ↓
fetch article content
         ↓
LLM classifies ContentType (6 options, enum-constrained, Haiku)
         ↓
LLM summarises into matched schema (Sonnet)
```

Default fallback if classification is uncertain: `ContentType.article`.

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
ingested_on: 2026-05-04
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

- Single command: user sends a URL (plain message or with optional note)
- Bot replies with: note title + tags + a one-line summary on success
- Bot replies with: error type + URL on failure (fetch error, parse error, schema validation error)
- Use webhook mode in production, polling in dev

---

## Vault index (vault_index.py)

- Reads all `.md` filenames from the vault at agent invocation time
- Strips `.md` extension, returns `list[str]` of note titles
- Passed into agent system prompt for link grounding
- Cache with a short TTL (60s) — vault doesn't change that fast

---

## Environment variables (.env)

```
ANTHROPIC_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=

# Vault — choose one mode
OBSIDIAN_VAULT_PATH=          # Option B: filesystem path
OBSIDIAN_API_KEY=             # Option A: REST API key
OBSIDIAN_BASE_URL=            # Option A: e.g. http://localhost:27123
```

---

## What to build first

1. `models.py` — already drafted, validate with a few manual Pydantic instantiations
2. `renderer.py` — pure function, easy to unit test, no LLM needed
3. `agent.py` — start with `ArticleNote` only, get the full loop working
4. `vault.py` — filesystem mode first, REST API later
5. `bot.py` — add Telegram last, use a CLI entrypoint during development

---

## Constraints and preferences

- Pseudocode before implementation on anything non-trivial
- Method-chaining style where it aids readability
- No placeholder text in `Reflection` fields — `None` is correct when uncertain
- `models.py` is append-only for new note types — never modify existing field names once the vault has notes using them (breaks frontmatter parsing)
- Keep `URL_ROUTING` updated as new domains are added
