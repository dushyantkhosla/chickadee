# Session Logs

## 2026-05-04 — Telegram bot (polling, queue, LM Studio auto-start)

**Plan executed:** `plans/2026-05-04-telegram-bot.md`

**What built/improved:**
- `src/bot.py` — full Telegram bot (polling, auth, typing indicator, stage-specific errors)
- `src/lmstudio_utils.py` — copied from skill, auto-starts server & loads model before LLM calls
- `src/agent.py` — `ensure_lm_studio()` called on first classify/summarise
- `src/main.py` — `run_pipeline()` returns `(path, note)` tuple for bot
- UX: immediate acknowledgment → per-chat deque queue → sequential processing
- **No dropped URLs** — all queued, processed in order, per user

**Changes:**
| File | What |
|---|---|
| `pyproject.toml` | +`python-telegram-bot>=21` |
| `src/config.py` | +`BOT_ALLOWED_CHAT_IDS` |
| `src/main.py` | return `(Path\|None, AnyNote)` |
| `src/lmstudio_utils.py` | new — server + model management |
| `src/agent.py` | auto-start LM Studio before LLM calls |
| `src/bot.py` | new — full bot with per-chat URL queue |
| `tests/test_bot.py` | new — 4 formatting tests |

**Test count:** 60 → **64 passed** (no regressions)

**TODO remaining:**
1. Obsidian REST API mode
2. Multimodal support
3. Richer link grounding
4. Implement frugal-lm skill

---

## 2026-05-05 — Docker + Remote LM Studio

**Plan executed:** `plans/2026-05-05-docker-remote-lmstudio.md`

**What built:**
- `src/lmstudio_client.py` — async HTTP client for LM Studio REST API (is_reachable, is_model_loaded, ensure_model_loaded, list_models)
- `src/lmstudio_utils.py` — deleted (was CLI/subprocess-based, won't work in Docker)
- `src/agent.py` — replaced ensure_lm_studio() with LMStudioClient
- `src/config.py` — added LM_STUDIO_API_KEY
- `src/exceptions.py` — added LMStudioError
- `Dockerfile` — multi-stage build (builder + runtime)
- `docker-compose.yml` — single service, vault bind-mount, restart policy
- `.dockerignore` — excludes .venv, .git, tests, etc.
- `README.md` — deployment instructions for Raspberry Pi
- `tests/test_lmstudio_client.py` — 7 new tests (all mock httpx)
- `tests/conftest.py` — auto-mocks lm_client for existing tests

**Commits:** 6 on `feat/docker-remote-lmstudio` branch
**Test count:** 64 → **71 passed**

**TODO remaining:**
1. Obsidian REST API mode
2. Multimodal support
3. Richer link grounding
4. Implement frugal-lm skill
