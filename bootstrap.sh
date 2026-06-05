#!/usr/bin/env bash
#
# bootstrap.sh — one-shot deploy of Chickadee.
#
# Usage:
#   1. Get a token from @BotFather on Telegram (/newbot)
#   2. Add to ~/.zshrc (or ~/.bashrc):
#        export CHICKADEE_TELEGRAM_BOT_TOKEN="<token>"
#   3. source ~/.zshrc
#   4. ./bootstrap.sh <logseq|obsidian>
#
# The vault lives at ./vault inside the project — no path env var needed.
# The argument determines both the renderer format and which web frontend starts.
#
# Re-runnable — safe to invoke again (idempotent).
# Ctrl-C during the log tail leaves the bot running.

set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_VAULT_DIR="${HOST_VAULT_DIR:-$REPO_DIR/vault}"

# ── Pretty output ──────────────────────────────────────────────────────
step() { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }
ok()   { printf "  \033[1;32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[1;33m!\033[0m %s\n" "$*"; }
die()  { printf "  \033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

# ── Frontend arg ──────────────────────────────────────────────────────
FRONTEND="${1:-}"

case "$FRONTEND" in
  logseq|obsidian) ;;
  *)
    printf "Usage: %s <logseq|obsidian>\n" "$(basename "$0")" >&2
    exit 1
    ;;
esac

# Derive vault backend from the argument — no separate env var needed.
export VAULT_FORMAT="$FRONTEND"
PROFILE="frontend-$FRONTEND"

# ── Preflight ──────────────────────────────────────────────────────────
step "Preflight checks"

# 1. Run from the repo root
[[ -f "$REPO_DIR/docker-compose.yml" ]] \
  || die "docker-compose.yml not found in $REPO_DIR — run this from the chickadee repo root."

# 2. Telegram token is mandatory
if [[ -z "${CHICKADEE_TELEGRAM_BOT_TOKEN:-}" ]]; then
  die "CHICKADEE_TELEGRAM_BOT_TOKEN is not set.

    Get one from @BotFather on Telegram (/newbot), then:
      echo 'export CHICKADEE_TELEGRAM_BOT_TOKEN=\"<token>\"' >> ~/.zshrc
      source ~/.zshrc
      ./bootstrap.sh"
fi
ok "CHICKADEE_TELEGRAM_BOT_TOKEN is set"

# 3. Docker daemon
command -v docker >/dev/null 2>&1 || die "docker not installed."
docker info >/dev/null 2>&1        || die "docker daemon not reachable. Try: sudo systemctl start docker"
ok "docker daemon is reachable"

# 4. docker compose (v2 plugin preferred, legacy fallback)
if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
else
  die "docker compose not found. Install the v2 plugin."
fi
ok "using: $COMPOSE_CMD"

# ── Provider summary ───────────────────────────────────────────────────
step "Provider configuration"

provider_status() {
  local name="$1" var="$2"
  if [[ -n "${!var:-}" ]]; then
    ok "  $name — set"
  else
    warn "  $name — not set (will be skipped)"
  fi
}

provider_status "LM Studio (tier 1, local)    " LM_STUDIO_BASE_URL
provider_status "Vercel AI Gateway (tier 2)   " VERCEL_AI_GATEWAY_API_KEY
provider_status "Cerebras (tier 3)            " CEREBRAS_API_KEY
provider_status "Ollama Cloud (tier 3)       " OLLAMA_API_KEY
provider_status "OpenRouter (tier 3 + YouTube)" OPENROUTER_API_KEY
provider_status "Groq (tier 3)                " GROQ_API_KEY

if [[ -z "${VERCEL_AI_GATEWAY_API_KEY:-}" && -z "${OPENROUTER_API_KEY:-}" ]]; then
  warn "Neither Vercel nor OpenRouter is set. Cloud fallback will not work — only local providers will respond."
fi
if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  warn "OPENROUTER_API_KEY is unset. YouTube URL transcription will fail."
fi

# ── Vault ──────────────────────────────────────────────────────────────
step "Preparing vault at $HOST_VAULT_DIR"

case "$FRONTEND" in
  obsidian) subdir="Inbox" ;;
  logseq)   subdir="pages" ;;
esac
ok "format: $VAULT_FORMAT (renderer writes to $subdir/)"

mkdir -p "$HOST_VAULT_DIR/$subdir"
ok "created $HOST_VAULT_DIR/$subdir"

# ── Build + start ──────────────────────────────────────────────────────
step "Building and starting containers (bot + $FRONTEND)"
cd "$REPO_DIR"
$COMPOSE_CMD --profile "$PROFILE" up -d --build
ok "containers are up"

# ── Status snapshot ────────────────────────────────────────────────────
step "Container status"
$COMPOSE_CMD --profile "$PROFILE" ps

# ── Tail logs ──────────────────────────────────────────────────────────
step "Tailing logs (Ctrl-C to detach — bot and $FRONTEND keep running)"
exec $COMPOSE_CMD --profile "$PROFILE" logs -f
