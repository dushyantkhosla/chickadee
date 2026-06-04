# Chickadee

Telegram bot that ingests URLs → fetches content → summarises with LLM → writes structured notes to a knowledge vault.

## Architecture

Single Docker container on a Raspberry Pi 4 (ARM64), polling Telegram, with a 3-tier LLM fallback chain:

| Priority | Provider | Model | Cost |
|---|---|---|---|
| 1 | LM Studio (laptop) | `gemma-4-e4b-it` | Free |
| 2 | Vercel AI Gateway | `openai/gpt-oss-20b` | $5/mo free tier |
| 3 | Free pool | Ollama, Groq, Cerebras, OpenRouter | Free |

LM Studio is probed via HTTP before each pipeline run. If the laptop is off or unreachable, it's skipped. YouTube transcription always uses OpenRouter (cloud-only).

Vault bind-mounted from host.

## Environment variables

All secrets are passed via shell environment — never commit `.env` to git.

Set these in `~/.zshrc` (or `~/.bashrc`):

```bash
# ── Required ────────────────────────────────────────────────────────────
export CHICKADEE_TELEGRAM_BOT_TOKEN="your-telegram-bot-token"
export TELEGRAM_WEBHOOK_SECRET=""  # optional, for webhook mode

# ── Telegram access control (optional, defaults to * = open access) ────
export BOT_ALLOWED_CHAT_IDS="*"  # or comma-separated chat IDs

# ── LM Studio — laptop, primary when available (optional) ──────────────
export LM_STUDIO_BASE_URL="http://192.168.1.52:1234/v1"
export LM_STUDIO_MODEL="gemma-4-e4b-it"

# ── Cloud fallback — at least one needed for reliability ────────────────
export VERCEL_AI_GATEWAY_API_KEY="your-vercel-key"
export OPENROUTER_API_KEY="your-openrouter-key"

# ── Free pool providers (optional) ─────────────────────────────────────
export GROQ_API_KEY="your-groq-key"
export CEREBRAS_API_KEY="your-cerebras-key"

# ── Vault ───────────────────────────────────────────────────────────────
export VAULT_BACKEND="obsidian"  # or "logseq"
export VAULT_PATH="/app/vault"  # inside container; host path mounted in compose
```

After editing, reload your shell:
```bash
source ~/.zshrc   # or source ~/.bashrc
```

Docker Compose reads these from the host shell and passes them into the container. No `.env` file needed.

See `.env.example` for the full list of available variables and their defaults.

## Deployment (Raspberry Pi)

### 1. Clone and configure

```bash
git clone <repo-url> /home/dushyant/code/chickadee
cd /home/dushyant/code/chickadee
```

Ensure the env vars above are set in your shell (see "Environment variables" section).

### 2. Create vault directory

```bash
mkdir -p /home/dushyant/code/chickadee/vault/Inbox
```

### 3. Build and start

```bash
docker compose up -d
```

### 4. Check logs

```bash
docker compose logs -f
```

### Rsync backup (optional)

```bash
# Cron job to sync vault to another machine
0 */6 * * * rsync -avz /home/dushyant/code/chickadee/vault/ user@backup:/path/to/vault/
```
