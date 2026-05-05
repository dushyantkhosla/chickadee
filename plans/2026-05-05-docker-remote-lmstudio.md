# Docker + Remote LMStudio — Spec & Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Containerize the Chickadee Telegram bot to run on a Raspberry Pi 4 (ARM64), with LM Studio running on a separate MacBook Air on the same LAN.

**Architecture:** Single Docker container on the Pi, polling Telegram, calling LM Studio REST API at `192.168.1.52:1234`. Vault bind-mounted from host. No webhooks, no reverse proxy.

**Tech Stack:** Docker, docker-compose, `python:3.13-slim` base image, `httpx` for LM Studio REST API, existing chickadee pipeline (PydanticAI, Obsidian vault)

---

## Spec

### LM Studio client

Replace `lmstudio_utils.py` (subprocess/CLI) with `lmstudio_client.py` (HTTP/REST).

New class `LMStudioClient` with methods:
- `is_reachable()` — `GET /api/v1/models`, return True if 200
- `is_model_loaded()` — check `loaded_instances` in response for configured model key
- `ensure_model_loaded()` — if not loaded, `POST /api/v1/models/load`
- `list_models()` — raw response for debugging

Raises `LMStudioError` on connection/load failure.

### Config

Add to `Settings`:
- `LM_STUDIO_API_KEY: str = ""` — optional, for authenticated LM Studio instances

`LM_STUDIO_BASE_URL` already exists. In Docker `.env`, set to `http://192.168.1.52:1234/v1`.

### Changes to existing files

- `agent.py`: remove `ensure_lm_studio()`, instantiate `LMStudioClient`, call `ensure_model_loaded()` before LLM calls
- `lmstudio_utils.py`: delete entirely
- `exceptions.py`: add `LMStudioError`

### Docker

**Dockerfile (multi-stage):**
- Stage 1 `builder`: `python:3.13-slim`, install `uv`, copy `pyproject.toml` + `uv.lock`, install deps
- Stage 2 `runtime`: `python:3.13-slim`, copy from builder, copy `src/`, set `CMD`

**docker-compose.yml:**
- Service: `chickadee`
- Build from Dockerfile
- Bind mount: `/home/dushyant/code/chickadee/vault:/app/vault`
- Env file: `.env`
- Restart: `unless-stopped`

**.dockerignore:** `.venv/`, `.git/`, `__pycache__/`, `*.pyc`, `.env`, `vault/`, `tests/`, `manage/`, `plans/`

### Testing

- `test_lmstudio_client.py` — mock `httpx` for all client methods + error cases
- Existing tests unchanged — all 58 should pass
- Manual: `docker compose up` on Pi → send URL → note in vault

### Files

| File | Action | Purpose |
|---|---|---|
| `src/lmstudio_client.py` | Create | HTTP client for LM Studio REST API |
| `src/lmstudio_utils.py` | Delete | Replaced by `lmstudio_client.py` |
| `src/agent.py` | Edit | Use `LMStudioClient` instead of `ensure_lm_studio()` |
| `src/config.py` | Edit | Add `LM_STUDIO_API_KEY` |
| `src/exceptions.py` | Edit | Add `LMStudioError` |
| `Dockerfile` | Create | Multi-stage container build |
| `docker-compose.yml` | Create | Orchestration with volume/env/restart |
| `.dockerignore` | Create | Exclude non-essential files from build context |
| `tests/test_lmstudio_client.py` | Create | Unit tests for new client |

---

## Plan

### Task 1: Add `LMStudioError` to exceptions

**Files:**
- Modify: `src/exceptions.py`

- [ ] **Step 1: Add exception class**

Add `LMStudioError(ChickadeeError)` to `src/exceptions.py`.

- [ ] **Step 2: Verify import**

Run: `python -c "from src.exceptions import LMStudioError"`
Expected: no error

- [ ] **Step 3: Commit**

```bash
git add src/exceptions.py
git commit -m "feat: add LMStudioError exception"
```

---

### Task 2: Create `lmstudio_client.py`

**Files:**
- Create: `src/lmstudio_client.py`
- Create: `tests/test_lmstudio_client.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_lmstudio_client.py` with tests for:
- `is_reachable()` — mock 200 response → True
- `is_reachable()` — mock connection error → False
- `is_model_loaded()` — mock response with loaded instance → True
- `is_model_loaded()` — mock response with empty loaded_instances → False
- `ensure_model_loaded()` — model already loaded → returns model key
- `ensure_model_loaded()` — model not loaded → calls POST load, returns model key
- `ensure_model_loaded()` — load fails → raises `LMStudioError`

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_lmstudio_client.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `lmstudio_client.py`**

Create `src/lmstudio_client.py`:
- Class `LMStudioClient` with `__init__(base_url, model_key, api_key)`
- Uses `httpx.AsyncClient` internally
- `is_reachable()`: GET `/api/v1/models`, return bool
- `is_model_loaded()`: GET `/api/v1/models`, check `loaded_instances` for model_key
- `ensure_model_loaded()`: check loaded, if not POST `/api/v1/models/load` with `{"model": model_key}`
- `list_models()`: GET `/api/v1/models`, return raw list
- Raise `LMStudioError` on HTTP errors or connection failures

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_lmstudio_client.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/lmstudio_client.py tests/test_lmstudio_client.py
git commit -m "feat: add LMStudioClient with REST API support"
```

---

### Task 3: Update config and agent

**Files:**
- Modify: `src/config.py`
- Modify: `src/agent.py`
- Delete: `src/lmstudio_utils.py`

- [ ] **Step 1: Add `LM_STUDIO_API_KEY` to config**

Add `LM_STUDIO_API_KEY: str = ""` to `Settings` in `src/config.py`.

- [ ] **Step 2: Update `agent.py`**

- Remove `from src.lmstudio_utils import ensure_model_loaded`
- Remove `ensure_lm_studio()` function
- Add: `from src.lmstudio_client import LMStudioClient`
- Create module-level `lm_client = LMStudioClient(settings.LM_STUDIO_BASE_URL, settings.LM_STUDIO_MODEL, settings.LM_STUDIO_API_KEY)`
- In `classify()`: replace `ensure_lm_studio()` with `await lm_client.ensure_model_loaded()`
- In `summarise()`: replace `ensure_lm_studio()` with `await lm_client.ensure_model_loaded()`

- [ ] **Step 3: Delete `lmstudio_utils.py`**

Run: `rm src/lmstudio_utils.py`

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/pytest -v`
Expected: all tests pass (existing 58 + new 7 = 65)

- [ ] **Step 5: Commit**

```bash
git add src/config.py src/agent.py
git rm src/lmstudio_utils.py
git commit -m "refactor: replace lmstudio_utils with LMStudioClient in agent"
```

---

### Task 4: Create Docker files

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

```
.venv/
.git/
__pycache__/
*.pyc
.env
vault/
tests/
manage/
plans/
*.md
.pytest_cache/
```

- [ ] **Step 2: Create `Dockerfile`**

Multi-stage build:
- Stage `builder`: `FROM python:3.13-slim`, install `uv` via pip, copy `pyproject.toml` + `uv.lock`, run `uv sync --no-dev`
- Stage `runtime`: `FROM python:3.13-slim`, copy from builder, copy `src/`, `CMD ["python", "-m", "src.bot"]`

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
services:
  chickadee:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - /home/dushyant/code/chickadee/vault:/app/vault
```

- [ ] **Step 4: Verify build**

Run: `docker compose build`
Expected: successful build

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: add Docker support for Raspberry Pi deployment"
```

---

### Task 5: Update `.env.example` and verify

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Update `.env.example`**

Ensure it includes:
```
LM_STUDIO_BASE_URL=http://192.168.1.52:1234/v1
LM_STUDIO_MODEL=your-model-key-here
LM_STUDIO_API_KEY=
```

- [ ] **Step 2: Run full test suite**

Run: `.venv/bin/pytest -v`
Expected: all 65 tests pass

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "chore: update .env.example with remote LMStudio defaults"
```

---

## Deployment

### On the Raspberry Pi

1. Clone the repo:
   ```bash
   git clone <repo-url> /home/dushyant/code/chickadee
   cd /home/dushyant/code/chickadee
   ```

2. Create `.env` with actual values:
   ```bash
   cp .env.example .env
   # Edit .env with real TELEGRAM_BOT_TOKEN, LM_STUDIO_MODEL, etc.
   # IMPORTANT: Set OBSIDIAN_VAULT_PATH=/app/vault (container path, not host path)
   ```

3. Create vault directory:
   ```bash
   mkdir -p /home/dushyant/code/chickadee/vault/Inbox
   ```

4. Build and start:
   ```bash
   docker compose up -d
   ```

5. Check logs:
   ```bash
   docker compose logs -f
   ```

### Key `.env` values for Docker

```
LM_STUDIO_BASE_URL=http://192.168.1.52:1234/v1
LM_STUDIO_MODEL=<your-model-key>
OBSIDIAN_VAULT_PATH=/app/vault
TELEGRAM_BOT_TOKEN=<your-token>
```

### On the MacBook (LM Studio)

1. Open LM Studio
2. Load the model configured in `LM_STUDIO_MODEL`
3. Ensure server is running on port 1234

### Rsync backup (optional)

```bash
# Cron job to sync vault to another machine
0 */6 * * * rsync -avz /home/dushyant/code/chickadee/vault/ user@backup:/path/to/vault/
```
