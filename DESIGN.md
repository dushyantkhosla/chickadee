# DESIGN.md — Structured Summarisation Pipeline

## Purpose

This document is the product backlog. Claude Code reads this to understand
build order, scope boundaries, and testing expectations. Each epic is a
self-contained vertical slice — implement, test, confirm, then move to the next.

Do not skip ahead. Do not build infrastructure that isn't needed by the current epic.
When an epic is complete, mark it `[x]` and summarise what was built in a `## Build log`
entry at the bottom of this file.

---

## System overview

```
CLI → Fetcher → Router → [Classifier] → Summariser → Renderer → Vault writer
                                ↑
                          Vault index
```

A URL goes in. A structured Markdown note comes out, filed into vault (Obsidian or Logseq).
See `CLAUDE.md` for file layout and coding conventions.
See `models.py` for all Pydantic schemas — do not redefine them elsewhere.

---

## Stack

- **Language:** Python 3.11+
- **LLM framework:** PydanticAI
- **LLM inference:** LM Studio (local, OpenAI-compatible API at `http://localhost:1234`)
- **HTTP:** `httpx` (async)
- **Testing:** `pytest` + `pytest-asyncio`
- **Config:** `pydantic-settings` reading from `.env`

---

## Epics

### Epic 1 — Project scaffold `[x]`

Stand up the repo structure, config, and dev environment. No LLM calls yet.

**Tasks**
- Create directory structure per `CLAUDE.md`
- `pyproject.toml` with all dependencies pinned
- `config.py` using `pydantic-settings`: reads `LM_STUDIO_BASE_URL`, `LM_STUDIO_MODEL`, `VAULT_PATH` from `.env`
- `main.py` CLI entrypoint: accepts a URL as argument, prints `"received: {url}"` and exits
- Confirm `models.py` imports cleanly — validate one `ArticleNote` instantiation in a smoke test

**Tests**
- `test_config.py` — settings load correctly from a test `.env`
- `test_models.py` — instantiate one of each note type with dummy data; assert all fields serialise to dict without error

**Done when:** `python main.py https://example.com` prints the URL; all tests pass.

---

### Epic 2 — Fetcher `[x]`

Retrieve raw text content from a URL. No LLM, no routing yet.

**Tasks**
- `fetcher.py`: async `fetch(url: str) -> str`
  - `httpx.AsyncClient` with a reasonable timeout and user-agent header
  - Strip HTML to readable text (use `trafilatura` — best-in-class for article extraction)
  - Raise typed exceptions: `FetchError`, `ParseError`
- For YouTube URLs: use `youtube-transcript-api` to fetch transcript instead of page HTML
- Log word count of fetched content

**Tests**
- `test_fetcher.py`
  - Mock `httpx` responses — test clean fetch, 404, timeout
  - Test YouTube URL detection triggers transcript path (mock the transcript API)
  - Assert output is a non-empty string

**Done when:** `fetcher.fetch("https://simonwillison.net/2025/...")` returns readable article text.

---

### Epic 3 — Router `[x]`

Determine `ContentType` from a URL without an LLM call where possible.

**Tasks**
- `router.py`: `route(url: str) -> ContentType | None`
  - Extract domain from URL
  - Look up `UNAMBIGUOUS_DOMAINS` from `models.py`
  - Return matched `ContentType` or `None` (signals: needs LLM classification)
  - `MULTI_TYPE_DOMAINS` is a guard — log a warning if a URL from this set somehow reaches the unambiguous path

**Tests**
- `test_router.py`
  - `youtube.com` → `ContentType.talk`
  - `arxiv.org` → `ContentType.paper`
  - `github.com` → `ContentType.repo`
  - `anthropic.com` → `None` (multi-type domain, needs classification)
  - `randomdomain.com` → `None` (unknown, needs classification)

**Done when:** all routing tests pass with zero LLM calls.

---

### Epic 4 — Classifier `[x]`

LLM-based content type classification for ambiguous URLs.
First LLM integration — use a small/fast model.

**Tasks**
- `agent.py`: async `classify(text: str) -> ContentType`
  - PydanticAI agent with LM Studio as the provider (OpenAI-compatible)
  - System prompt: explain the 6 content types with one-line descriptions
  - Output schema: `ContentType` enum — constrained, not free text
  - Default to `ContentType.article` if confidence is low
- Wire into `main.py`: if `router.route()` returns `None`, call `classifier.classify()`

**Tests**
- `test_classifier.py`
  - Mock LM Studio responses — assert correct `ContentType` is returned for representative snippets of each type
  - Assert fallback to `ContentType.article` on ambiguous input

**Done when:** `main.py` can route any URL to a `ContentType` with or without an LLM call.

---

### Epic 5 — Summariser `[x]`

Core LLM call. Given content + `ContentType`, return a typed `*Note` object.

**Tasks**
- `agent.py`: async `summarise(text: str, content_type: ContentType, vault_titles: list[str]) -> AnyNote`
  - PydanticAI agent, main model (larger than classifier)
  - System prompt includes:
    - The matched note type schema with field descriptions
    - The vault titles list for link grounding
    - Instruction: populate `builds_on`, `see_also`, `contradicts` from vault titles only — exact match, no invention
    - Instruction: leave `Reflection` fields as `None` — do not generate filler
  - Output schema: the specific `*Note` type (not `AnyNote` union — pass the resolved type)
- Classification and summarisation are always separate calls — never combined

**Tests**
- `test_summariser.py`
  - Mock LM Studio — assert returned object is the correct `*Note` type
  - Assert `builds_on` only contains titles from the passed vault list
  - Assert `Reflection` fields are `None` when not inferable
  - Test each of the 6 note types with representative fixture text

**Done when:** `summarise()` returns a valid, validated Pydantic object for each note type.

---

### Epic 6 — Renderer `[x]`

Convert a `*Note` object to an Obsidian-compatible Markdown string. Pure function, no LLM.

**Tasks**
- `renderer.py`: `render(note: AnyNote) -> str`
  - YAML frontmatter block: tags, link fields wrapped in `[[...]]`, source_url, source_type, ingested_on
  - Body sections vary by type — see `CLAUDE.md` for template structure
  - `Reflection` section always present; skip individual fields if `None`
  - `open_questions` section always present; omit section if list is empty
  - For `FieldNote`: add `## Data points`, `## Code`, `**Author's take:**`, `**Shelf life:**`

**Tests**
- `test_renderer.py`
  - Render one of each note type from a fixture object
  - Assert frontmatter is valid YAML (parse with `pyyaml`)
  - Assert wikilinks are formatted as `[[Title]]`
  - Assert `None` Reflection fields are omitted from output
  - Assert empty `open_questions` omits the section entirely

**Done when:** `render(note)` produces valid, human-readable Markdown for all 6 types.

---

### Epic 7 — Vault writer + Vault index `[x]`

Write the rendered note to the Obsidian vault. Read existing note titles for link grounding.

**Tasks**
- `vault.py`: `write(filename: str, content: str) -> Path`
  - Write to `{VAULT_PATH}/Inbox/{filename}`
  - Create `Inbox/` if it doesn't exist
  - Filename format: `{YYYY-MM-DD}_{slugified-title}.md`
  - Raise `VaultWriteError` on failure
- `vault_index.py`: `get_titles() -> list[str]`
  - Walk vault directory, collect all `.md` filenames
  - Strip `.md` extension
  - Cache with 60s TTL — vault doesn't change that fast
  - Exclude `Inbox/` from index (in-flight notes shouldn't self-reference)

**Tests**
- `test_vault.py`
  - Write a note to a temp directory; assert file exists with correct content
  - Assert `Inbox/` is created if absent
  - Assert filename slugification is correct
- `test_vault_index.py`
  - Seed a temp vault with `.md` files; assert titles returned correctly
  - Assert `Inbox/` files are excluded
  - Assert cache returns same result within TTL

**Done when:** a note is written to the vault and readable in Obsidian.

---

### Epic 8 — Integration: full pipeline `[x]`

Wire all epics into a single end-to-end flow. This is the MVP completion milestone.

**Tasks**
- `main.py`: full pipeline
  ```
  url → fetch → route → [classify] → vault_index → summarise → render → write
  ```
- Print on success: note title, type, tags, and file path
- Print on failure: which stage failed and why
- Add `--dry-run` flag: runs everything except vault write, prints rendered Markdown to stdout

**Integration tests**
- `test_integration.py`
  - Mock fetcher + LM Studio; run full pipeline for one URL of each content type
  - Assert correct note type produced
  - Assert file written to temp vault
  - Assert `--dry-run` does not write a file

**Done when:** `python main.py https://simonwillison.net/...` produces a note in the vault.

---

## Backlog — future enhancements

Not in MVP. Implement after Epic 8 is complete and stable.

### Telegram integration
- Webhook bot: user sends URL via Telegram, receives confirmation with note title + tags
- Use `python-telegram-bot` or `aiogram`
- Deploy considerations: needs a public webhook endpoint (ngrok for dev, VPS/cloud for prod)

### Multimodal support
- YouTube videos currently use transcript only — add frame extraction for visual content
- PDF ingestion: `pymupdf` for text extraction; treat as `PaperNote` by default
- Image-heavy articles: pass screenshots to vision model alongside text

### Richer link grounding
- Current approach: pass all vault titles to LLM (works up to ~2k notes)
- At scale: embed vault note summaries, retrieve top-k candidates before summarisation
- Stack: `sentence-transformers` + local vector store (`chromadb` or `lancedb`)

### Obsidian pro-usage tips
- Use **Dataview** plugin to query frontmatter fields — e.g. all `FieldNote`s with `shelf_life: days` ingested in the last 7 days
- Use **Graph view** filters to isolate `builds_on` / `contradicts` edges from `see_also` (noisier)
- `Inbox/` as a triage folder — review weekly, promote notes to topic folders, backfill `Reflection` manually
- Tag taxonomy: keep `tags` broad (topic), use `source_type` for filtering by content type — don't duplicate in tags
- **Templater** plugin can auto-open new `Inbox/` notes for Reflection completion

---

## Build log

### 2026-05-04 — Epics 1–8 complete (MVP shipped)

**Epic 1** — Scaffold: `pyproject.toml`, `config.py` (pydantic-settings + `.env`), `models.py` (6 note types + `AnyNote` union), `exceptions.py`, smoke tests.

**Epic 2** — Fetcher: `fetcher.py` with `httpx` + `trafilatura` for HTML, `youtube-transcript-api` for YouTube. Typed `FetchError`/`ParseError`.

**Epic 3** — Router: `router.py` extracts domain, maps `UNAMBIGUOUS_DOMAINS` to `ContentType`, returns `None` for multi-type/unknown domains.

**Epic 4** — Classifier: `agent.py` `classify()` using PydanticAI + LM Studio (OpenAI-compatible), outputs `ContentType` enum, falls back to `article` on error.

**Epic 5** — Summariser: `agent.py` `summarise()` dispatches to correct `*Note` schema via PydanticAI. Prompt includes vault titles for link grounding, instructs `None` Reflection fields (no filler).

**Epic 6** — Renderer: `renderer.py` pure function `AnyNote → str`. YAML frontmatter with `[[wikilinks]]`, type-specific body sections, omits empty `open_questions` and `None` reflection fields.

**Epic 7** — Vault: `vault.py` writes `{YYYY-MM-DD}_{slug}.md` to `Inbox/`, `VaultWriteError` on failure. `vault_index.py` walks `.md` files, 60s TTL cache, excludes `Inbox/`.

**Epic 8** — Integration: `main.py` full async pipeline `fetch → route → classify → index → summarise → render → write`. `--dry-run` skips disk write. 58 tests covering all 6 note types, error paths, and end-to-end flow.

**Test count:** 58 passing (`test_config` 4, `test_models` 6, `test_fetcher` 6, `test_router` 10, `test_classifier` 5, `test_main` 2, `test_summariser` 8, `test_renderer` 8, `test_vault` 3, `test_vault_index` 2, `test_integration` 2).
