# Chickadee

Telegram bot that ingests URLs → fetches content → summarises with LLM → writes structured notes to an Obsidian vault.

## Architecture

Single Docker container on a Raspberry Pi 4 (ARM64), polling Telegram, calling LM Studio REST API on a MacBook Air on the same LAN. Vault bind-mounted from host.

## Deployment (Raspberry Pi)

### 1. Clone and configure

```bash
git clone <repo-url> /home/dushyant/code/chickadee
cd /home/dushyant/code/chickadee
cp .env.example .env
```

Edit `.env` with real values:

```
TELEGRAM_BOT_TOKEN=<your-token>
LM_STUDIO_BASE_URL=http://192.168.1.52:1234/v1
LM_STUDIO_MODEL=<your-model-key>
OBSIDIAN_VAULT_PATH=/app/vault
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

### 5. On the MacBook (LM Studio)

1. Open LM Studio
2. Load the model configured in `LM_STUDIO_MODEL`
3. Ensure server is running on port 1234

### Rsync backup (optional)

```bash
# Cron job to sync vault to another machine
0 */6 * * * rsync -avz /home/dushyant/code/chickadee/vault/ user@backup:/path/to/vault/
```
