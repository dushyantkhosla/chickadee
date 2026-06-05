# Chickadee

> One human action (send a link). Everything else is automated.

Chickadee is a Telegram bot that turns URLs into structured notes in your
[Obsidian](https://obsidian.md) or [Logseq](https://logseq.com) vault. Send
it a link, get back a Markdown file shaped the way *that kind of content*
should be shaped — with the right fields, the right sections, and links
grounded in the notes you already have.

## Why

You share links in chat all day. Most of them you'll never revisit. The ones
that matter, you want to actually *think about* — not just bookmark.

Existing options each miss something:

- **Bookmarking services** (Pocket, Raindrop) — no synthesis. Save → forget.
- **Read-later apps** (Matter, Instapaper) — you read in *their* app, not
  in your knowledge system. Highlights get trapped in someone else's silo.
- **Readwise Reader / Matter AI summaries** — they summarise, but the
  output lives in *their* system. To get it into your vault, you
  copy-paste, reformat, lose links.
- **Manual note-taking** — the best long-term outcome, but high friction.
  Most links don't make it.

Chickadee's two insights:

1. **The note type matters.** A YouTube talk and an arXiv paper want
   different structures. A Substack essay and a GitHub repo want different
   questions answered. OneNote-style "everything is a page" loses that.
2. **Link grounding matters.** A summary that links to "the transformer
   paper" is useless. A summary that links to `[[Attention Is All You
   Need]]` — the actual note in your vault — is gold.

## What you get back

A Markdown file with the right shape for the content. Six types —
`TalkNote` for talks, `ArticleNote` for general articles, `PaperNote` for
academic papers, `EssayNote` for opinion/long-form, `RepoNote` for GitHub
repos, `FieldNote` for practitioner field reports.

Example — an article ingested into Obsidian:

```markdown
---
tags: [llm, evals, prompt-caching]
builds_on: ["[[Prompt Caching in Production]]"]
see_also: ["[[Anthropic Prompt Caching Notes]]"]
contradicts: []
source_url: https://simonwillison.net/2025/May/...
source_type: article
ingested_on: 2026-06-04
upload_date: 2025-05-15
---

# Notes on Claude's New Prompt Caching Behaviour

_Simon Willison_

## Summary
Anthropic's prompt caching now applies automatically without an explicit
cache breakpoint, which changes the cost calculus for long-context
applications in ways that aren't yet obvious from the docs.

## Key points
- Cache hits are now detected by prefix matching alone — no breakpoint required
- 5-minute TTL by default; 1-hour TTL is opt-in and 2x the write cost
- Multi-turn conversations are now cheaper than their single-shot equivalent

## Evidence
- Re-running the same 12k-token system prompt 50×: first call 18¢, subsequent 2¢
- GitHub issue #4521 confirms the breakpoint-free behaviour was undocumented at release

## Open questions
- What's the failure mode when the cache key collides on a near-prefix?
- Does this compose with tool-use result caching?

## Reflection
**My take:** Real lever for agent cost, not just a marketing update.
**So what:** Re-running a 12k-token prompt on every agent step was
prohibitive. Now it's table-stakes.
**Now what:** Re-benchmark my agent harness with caching on; check whether
the tool-use result cache can be replaced with this.
```

A talk looks different — speaker, ordered arguments, key quotes:

```markdown
---
tags: [interpretability, sparse-autoencoders, anthropic]
builds_on: ["[[Towards Monosemanticity]]"]
see_also: ["[[Scaling Monosemanticity]]"]
contradicts: []
source_url: https://www.youtube.com/watch?v=...
source_type: talk
ingested_on: 2026-06-04
upload_date: 2025-04-22
---

# Scaling Sparse Autoencoders: What Works at GPT-4 Scale

_Tristan Hume (Anthropic)_

## Summary
Sparse autoencoders trained on Claude 3's residual stream recover
interpretable features, but the engineering required at frontier-model
scale is non-trivial and not a straightforward extrapolation from toy
models.

## Arguments
1. At 1B parameters, SAEs recover ~80% of monosemantic features the team
   identified by hand
2. Scaling to 7B introduces training instabilities that don't appear in
   smaller runs
3. The dead-latent problem (≤5% of features activate in any given context)
   worsens with scale
4. Resampling dead latants during training recovers coverage but introduces
   its own artefacts

## Key quotes
> "The features you can name are not a representative sample of the
> features that exist."

## Open questions
- Is there a fundamental ceiling on monosemantic feature recovery, or is
  it an optimisation problem?

## Reflection
**My take:** Strongest evidence yet that SAE interpretability is real work,
not a toy.
**Now what:** Read the related paper; revisit my own activation-patching
experiments.
```

The full set of type-specific fields and sections is documented in
[AGENTS.md](AGENTS.md#models-modelspy).

## How it works

Six steps. Routing is two-tier — domain alone decides high-confidence
cases (YouTube → talk, arXiv → paper, GitHub → repo), and everything
else is classified by a cheap LLM call *before* summarisation.

```
URL
  │
  ▼
1. ROUTE
   ├─ Tier 1: domain is unambiguous → ContentType decided
   │           (youtube.com, arxiv.org, doi.org, github.com, vimeo.com)
   └─ Tier 2: fetch first, then LLM-classify (6-way enum)
  │
  ▼
2. FETCH
   ├─ YouTube: yt-dlp (with cookies.txt) → audio → OpenRouter multimodal transcription
   └─ Web:    httpx GET → trafilatura extract
  │
  ▼
3. CLASSIFY    (Tier 2 only — one cheap LLM call, enum-constrained)
  │
  ▼
4. SUMMARISE   (typed Pydantic model, ContentType injected explicitly)
   └─ Vault titles injected for link grounding — no hallucinated links
  │
  ▼
5. RENDER      (AnyNote → Markdown)
   ├─ Obsidian mode: YAML frontmatter + [[wikilinks]]
   └─ Logseq mode:   property:: value lines + [[wikilinks]]
  │
  ▼
6. WRITE
   ├─ Obsidian → {vault}/Inbox/{date}_{slug}.md
   └─ Logseq   → {vault}/pages/{slug}.md
```

**Why two separate LLM calls in Tier 2?** A single combined
"classify-and-summarise" call causes the model to anchor on the wrong
type early. Splitting them is cheap and dramatically improves schema
fidelity.

**Why inject the resolved `ContentType` into summarisation?** Because
trusting the model to infer it from the URL or content is exactly how
you end up with a Substack opinion piece summarised as a paper.

**Why a separate classification enum call?** A 6-way enum-constrained
classification is fast, cheap, and forces the model to commit to a type
before committing to content. The downstream summariser then knows which
schema to use.

## Architecture

Single Docker container, polls Telegram, 3-tier LLM fallback chain:

| Priority | Provider | Model | Cost |
|---|---|---|---|
| 1 | LM Studio (laptop) | `gemma-4-e4b-it` | Free |
| 2 | Vercel AI Gateway | `openai/gpt-oss-20b` | $5/mo free tier |
| 3 | Free pool | Ollama, Groq, Cerebras, OpenRouter | Free |

LM Studio is probed via HTTP before each pipeline run. If the laptop is
off or unreachable, it's skipped silently. YouTube transcription always
uses OpenRouter (cloud-only — no local transcription fallback).

The vault is bind-mounted from the host. All secrets come from the host
shell environment; nothing is committed.

## Environment variables

All secrets are passed via shell environment — never commit `.env` to git.

Set these in `~/.zshrc` (or `~/.bashrc`):

```bash
# ── Required ───────────────────────────────────────────────────────────────
export CHICKADEE_TELEGRAM_BOT_TOKEN="your-telegram-bot-token"
export TELEGRAM_WEBHOOK_SECRET=""  # optional, for webhook mode

# ── Telegram access control (optional, defaults to * = open access) ────
export CHICKADEE_ALLOWED_CHAT_IDS="*"  # or comma-separated chat IDs

# ── LM Studio — laptop, primary when available (optional) ──────────────
export LM_STUDIO_BASE_URL="http://192.168.1.52:1234/v1"
export LM_STUDIO_MODEL="gemma-4-e4b-it"

# ── Cloud fallback — at least one needed for reliability ──────────────
export VERCEL_AI_GATEWAY_API_KEY="your-vercel-key"
export OPENROUTER_API_KEY="your-openrouter-key"

# ── Free pool providers (optional) ─────────────────────────────────────
export GROQ_API_KEY="your-groq-key"
export CEREBRAS_API_KEY="your-cerebras-key"

# ── Vault ──────────────────────────────────────────────────────────────
export VAULT_FORMAT="obsidian"  # or "logseq" — controls the renderer format
# The vault itself is always ./vault inside the project. No path env var needed.
```

After editing, reload your shell:

```bash
source ~/.zshrc   # or source ~/.bashrc
```

Docker Compose reads these from the host shell and passes them into the
container. No `.env` file needed. See `.env.example` for the full list of
available variables and their defaults.

## Deployment

Runs anywhere Docker runs. Tested on a Raspberry Pi 4 (ARM64).

```bash
# 1. Clone
git clone <repo-url> /home/dushyant/code/chickadee
cd /home/dushyant/code/chickadee

# 2. Create vault directory
mkdir -p /home/dushyant/code/chickadee/vault/Inbox

# 3. Build and start
docker compose up -d

# 4. Check logs
docker compose logs -f
```

Optional rsync backup of the vault:

```bash
# Cron job to sync vault to another machine
0 */6 * * * rsync -avz /home/dushyant/code/chickadee/vault/ user@backup:/path/to/vault/
```

## YouTube cookies

YouTube bot detection can block requests or serve CAPTCHAs when fetching
videos. To avoid this, yt-dlp uses a `cookies.txt` file with your browser's
session cookies. The cookie file is already configured in the codebase —
you just need to provide it.

### How it works

`src/transcriber.py` checks for cookies in this order:
1. `/app/cookies.txt` — Docker (bind-mounted from host)
2. `./cookies.txt` — local dev (project root)
3. Brave browser — local dev only (via `cookiesfrombrowser`)

The file is mounted as read-only in `docker-compose.yml`.

### Generate cookies.txt

1. Install the browser extension [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) (Chrome) or [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/) (Firefox)
2. Open Brave/Chrome/Firefox and go to [youtube.com](https://youtube.com)
3. Make sure you're **logged in** to your Google account
4. Click the extension icon → **Export** → save as `cookies.txt`
5. Place the file in the project root:

```bash
# Local dev
~/code/chickadee/cookies.txt

# Server (copy via scp)
scp cookies.txt user@server:~/chickadee/
```

6. Restart the container:

```bash
docker compose restart
```

### When cookies expire

YouTube cookies typically last **3-6 months**. Signs of expiry:
- yt-dlp returns HTTP 403 errors
- Bot reports `yt-dlp failed: Sign in to confirm you're not a bot`
- Downloaded audio is empty or corrupt

To fix: re-export cookies using the same steps above and replace the file
on the server.

### Security

`cookies.txt` contains your session token — **never commit it to git**.
It's already in `.gitignore`. Anyone with this file can impersonate your
Google account on YouTube.

## Documentation map

- **[AGENTS.md](AGENTS.md)** — internal manual for the AI agent working in
  this repo. Full model schemas, routing rules, prompt design, constraints.
  Read this if you're going to change code.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — entry point for new contributors.
  The rules that have caused real bugs when violated.
- **[GLOSSARY.md](GLOSSARY.md)** — the project's domain vocabulary. Use
  these terms consistently in code, comments, and commits.
- **[docs/adr/](docs/adr/)** — architecture decision records. Start here
  for the reasoning behind non-obvious choices.
  - [0001 — Logseq vault backend](docs/adr/0001-logseq-vault-backend.md)
