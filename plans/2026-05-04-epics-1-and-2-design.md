# Design — Epics 1 & 2: Project Scaffold + Fetcher

## Scope

Implement Epics 1 and 2 from `DESIGN.md` only. Epics 3–8 remain on the backlog.

## Epic 1 — Project Scaffold

### Deliverables

| File | Action | Purpose |
|---|---|---|
| `pyproject.toml` | Edit | Add runtime and test dependencies |
| `src/config.py` | Create | `pydantic-settings` reading `.env`; `OBSIDIAN_VAULT_PATH` defaults to `/tmp/chickadee-vault` (placeholder) |
| `src/main.py` | Create | CLI entrypoint: `python -m src.main <url>` prints `"received: {url}"` and exits |
| `src/exceptions.py` | Create | Shared exceptions: `FetchError`, `ParseError` |
| `tests/test_config.py` | Create | Load settings from temp `.env`; assert values match |
| `tests/test_models.py` | Create | Instantiate one of each `*Note` type with dummy data; assert `.model_dump()` succeeds |

### Dependencies to add

```
httpx
trafilatura
youtube-transcript-api
pydantic-settings
python-dotenv
python-slugify
pytest
pytest-asyncio
```

### Done when
- `python src/main.py https://example.com` prints the URL
- `pytest tests/` passes for `test_config.py` and `test_models.py`

---

## Epic 2 — Fetcher

### Deliverables

| File | Purpose |
|---|---|
| `src/fetcher.py` | `async fetch(url: str) -> str`; `httpx.AsyncClient` + `trafilatura` for HTML; `youtube-transcript-api` for YouTube URLs; typed exceptions |
| `tests/test_fetcher.py` | Mock HTTP 200/404/timeout; mock transcript API; assert non-empty string output |

### Behaviour

- Extract domain from URL
- YouTube URLs (`youtube.com`, `youtu.be`) → transcript API path
- Everything else → `httpx` GET → `trafilatura.extract()` → plain text
- Log word count of fetched content
- Raise `FetchError` on HTTP failure, `ParseError` on extraction failure

### Done when
- `fetcher.fetch("https://simonwillison.net/2025/...")` returns readable article text
- `pytest tests/test_fetcher.py` passes

---

## Directory layout after completion

```
.
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── models.py          (exists)
│   ├── fetcher.py
│   └── exceptions.py
├── tests/
│   ├── test_config.py
│   ├── test_models.py
│   └── test_fetcher.py
└── plans/
    └── 2026-05-04-epics-1-and-2-design.md   (this file)
```

---

## Constraints

- `models.py` is append-only — never modify existing field names
- No placeholder text in `Reflection` fields — `None` is correct when uncertain
- `OBSIDIAN_VAULT_PATH` is a placeholder; user will update `config.py` later
