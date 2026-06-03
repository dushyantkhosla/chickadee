# Chickadee

Telegram bot that ingests URLs → fetches content → summarises with LLM → writes structured notes to an Obsidian vault.

## Architecture

Single Docker container on a Raspberry Pi 4 (ARM64), polling Telegram, with a 3-tier LLM fallback chain:

| Priority | Provider | Model | Cost |
|---|---|---|---|
| 1 | LM Studio (laptop) | `gemma-4-e4b-it` | Free |
| 2 | Vercel AI Gateway | `openai/gpt-oss-20b` | $5/mo free tier |
| 3 | Free pool | Ollama, Groq, Cerebras, OpenRouter | Free |

LM Studio is probed via HTTP before each pipeline run. If the laptop is off or unreachable, it's skipped. YouTube transcription always uses OpenRouter (cloud-only).

Vault bind-mounted from host.

## Deployment (Raspberry Pi)

### 1. Clone and configure

```bash
git clone <repo-url> /home/dushyant/code/chickadee
cd /home/dushyant/code/chickadee
cp .env.example .env
```

Edit `.env` with real values. Required:

```bash
TELEGRAM_BOT_TOKEN=<your-token>
OBSIDIAN_VAULT_PATH=/app/vault
```

For local LLM (when laptop is on):
```bash
LM_STUDIO_BASE_URL=http://192.168.1.52:1234/v1
LM_STUDIO_MODEL=gemma-4-e4b-it
```

For cloud fallback (at least one needed):
```bash
VERCEL_AI_GATEWAY_API_KEY=<your-key>
OPENROUTER_API_KEY=<your-key>
```

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
