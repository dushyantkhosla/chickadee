# Contributing to Chickadee

Thanks for your interest. This is the contributor's entry point. For the
internal details (full model schemas, provider chain wiring, prompt
design), read [AGENTS.md](AGENTS.md) alongside this — it goes deeper on
the *why* behind many of the rules below.

For the project vocabulary, see [GLOSSARY.md](GLOSSARY.md).

## What Chickadee does

Telegram bot → fetches URL → classifies & summarises with LLM → writes a
typed Markdown note to your Obsidian or Logseq vault. Full description in
the [README](README.md#why).

## Local setup

```bash
# Clone
git clone <repo-url> /home/dushyant/code/chickadee
cd /home/dushyant/code/chickadee

# Install deps (uses uv)
uv sync

# Set the env vars you need (see README "Environment variables")
export CHICKADEE_TELEGRAM_BOT_TOKEN="..."
export OPENROUTER_API_KEY="..."   # at minimum, you need a cloud provider
# ... etc.

# Run a single URL through the pipeline (CLI mode)
uv run python -m src.main https://example.com/article

# Or run the bot
uv run python -m src.bot
```

## Project rules (the constraints that matter)

These are non-obvious and have caused real bugs when violated. Read
before opening a PR.

### 1. `src/models.py` is append-only for new note types

Field names in existing note types must never be renamed or removed. The
vault contains notes that depend on the exact YAML key names (`tags`,
`builds_on`, `source_url`, `source_type`, etc.) — renaming a field breaks
every existing note's frontmatter parsing in Obsidian and Logseq.

To add a new note type or a new field, **append**. Don't edit.

If you're modifying `models.py` (additively only), say so explicitly in
the PR description so the "append-only" invariant is on the record.

### 2. Classification and summarisation are two separate LLM calls

The agent runs `classify()` first, then `summarise()` with the resolved
`ContentType` injected explicitly. Doing both in one call causes the
model to anchor on the wrong type early (a Substack post gets
summarisation as a paper, a YouTube description gets summarised as a
field note, etc.).

The two-call pattern is enforced in `src/agent.py`. Don't collapse it.

### 3. Two-tier routing — read the rules before adding domains

`UNAMBIGUOUS_DOMAINS` in `src/models.py` is the domain → type mapping
for high-confidence cases (YouTube → talk, arXiv → paper, GitHub →
repo, etc.). `MULTI_TYPE_DOMAINS` is a guard rail: known domains where
the article type varies per post (e.g. `simonwillison.net` mixes essays,
field notes, and articles).

Anything in `MULTI_TYPE_DOMAINS` **must not** be moved to
`UNAMBIGUOUS_DOMAINS`, even if a pattern seems tempting — the per-post
variation is the point.

Default fallback type when classification is uncertain:
`ContentType.article`.

### 4. `Reflection` fields are `None` or real — never padded

When the LLM doesn't have a strong basis for `my_take`, `so_what`, or
`now_what`, it must leave them `None`. The renderer omits `None` fields.
A generic "interesting article" placeholder is worse than nothing — it
kills trust in the reflection block.

If you see the LLM padding these fields, tighten the prompt or change
the model choice; don't relax the rule.

### 5. Pass the resolved `ContentType` into summarisation explicitly

Never ask the summarisation model to infer the type from the URL or the
content — it has already been decided. Pass it as a typed parameter so
the model can't go off-script.

### 6. Guide the model on the nested `meta` object

Small open-weight models flatten `meta.tags` into `meta_tags` if not
told otherwise. The summarisation prompt must include a schema sketch
that names the nested fields explicitly.

### 7. Link grounding — never invent note titles

`src/vault_index.py` reads the titles of all existing notes in the
vault. These are passed into the summarisation prompt. The model must
populate `builds_on`, `see_also`, and `contradicts` **only** with exact
titles from this list. Empty lists are correct when there's no
confident match.

If the prompt doesn't explicitly say "no hallucinated titles", models
will invent plausible-sounding ones (`[[The Original Transformer
Paper]]`) and they'll never resolve.

### 8. Type-specific prompting details

- `TalkNote`: the LLM should use the title/speaker from context. Don't
  say "do NOT produce" — `title` and `speaker` are required fields.
- `PaperNote`: follow IMRaD — `hypothesis` → `methodology` → `findings`
  → `limitations`.
- `EssayNote`: actively separate `claimed` (opinion/intuition) from
  `evidenced` (data/citations). The point of the type is the
  separation.
- `FieldNote.authors_take`: must be the author's informed opinion, not
  reported facts. If you can't tell, leave `None`.

## Tests

Run `pytest` before committing. All tests must pass.

```bash
uv run pytest
```

The renderer tests (`tests/test_renderer.py`) are a good way to verify
frontmatter/property output for any new note type — add a test alongside.

## Process

- Pseudocode before implementation on anything non-trivial
- Keep PRs scoped — one logical change, one set of changes
- Touching `src/models.py`? Say so in the PR description.
- Adding a new note type? Add a renderer test in `tests/test_renderer.py`
  and update the routing tables in `src/models.py`.
- Adding a new vault backend or non-trivial architectural choice? Open an
  ADR in `docs/adr/` (next available number, kebab-case slug).
