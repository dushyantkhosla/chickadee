# AGENTS.md — Structured Summarisation Pipeline

## Project Overview
Build a local‑first, private “thinking inbox” that accepts a URL via Telegram, downloads the content, generates a structured summary using a **local LLM (LMStudio)**, and files a richly‑linked Markdown note into an **Obsidian vault** via the Local REST API.

The central specification (`spec.md`) defines the universal output schema, content‑type taxonomy, Markdown rendering, and all integration points. **All design decisions have been made.** Follow them exactly.

## Core Constraints
- **Local LLM only** – LMStudio with an OpenAI‑compatible endpoint. No external APIs for inference.
- **Development target**: Macbook, testing locally.
- **Production target**: Ubuntu Server on Raspberry Pi (4 or 5).
- **Network**: All communication is LAN or Tailscale. No internet‑exposed endpoints except Telegram (which is internet‑facing by nature).
- **Telegram bot** must use long polling (simplest for the Pi). No webhooks.
- **Single worker, async/await**.

## Technology Stack
| Component | Library / Tool |
|-----------|----------------|
| Bot framework | `python-telegram-bot` (v20+, async) |
| Content extraction | `trafilatura` (articles), `youtube-transcript-api` (videos) |
| LLM agent | `pydantic-ai` |
| LLM endpoint | LMStudio (`http://<host>:1234/v1`) |
| HTTP client | `httpx` (async) |
| Templating | `jinja2` |
| Obsidian integration | REST calls to the Obsidian Local REST API plugin |
| Config management | `python-dotenv` (`.env` file) |
| Process manager | `systemd` (for deployment) |

## Repository Layout (Suggested)

```
.
├── AGENTS.md
├── spec.md
├── .env.example
├── main.py # entry point
├── src/
│ ├── bot.py # telegram bot handlers
│ ├── fetcher.py # content extraction
│ ├── summarizer.py # pydantic-ai agent & prompt
│ ├── models.py # Pydantic models (exactly from spec)
│ ├── renderer.py # Jinja2 → Markdown
│ └── obsidian.py # Obsidian API client
├── tests/
│ ├── test_classification.py
│ ├── test_models.py
│ ├── test_renderer.py
│ └── test_integration.py
└── templates/
└── note.md.j2 # Markdown template
```

## Implementation Order
1. **`models.py`** – Translate the Pydantic models in `spec.md` Section 4.2 exactly. Include all validation (length limits, mandatory/optional logic).
2. **`fetcher.py`** – Implement `fetch_content(url)` returning raw text + metadata (title, author, date). Handle YouTube transcripts, `trafilatura` for HTML, and direct plain text.
3. **`summarizer.py`** – Create the `pydantic-ai` Agent. Hardcode the system prompt following the content‑type taxonomy, routing logic, and output schema from the spec. The agent must return a `StructuredSummary` object.
4. **`renderer.py`** + `templates/note.md.j2` – Build the Markdown renderer. It must check `content_type` and only render the non‑null type‑specific block, in the exact order specified.
5. **`obsidian.py`** – A simple async function to POST the rendered Markdown to the Obsidian Local REST API with authentication.
6. **`bot.py`** – Wire up the Telegram bot: on message containing a URL → fetch → summarise → render → push → reply.
7. **`main.py`** – Load `.env`, start the bot (polling), graceful shutdown.
8. **Deployment** – Write a `systemd` unit file (example in spec) and a setup script.

## Testing Strategy
- **Unit tests** must cover:
  - Classification accuracy (given mock excerpts, verify `content_type` and `rhetorical_stance`).
  - Model validation (valid JSON, boundary checks, mandatory fields).
  - Renderer output (correct frontmatter, wikilinks, section order).
- **Integration tests** (run against a live LMStudio + Obsidian):
  - Use the exact acceptance criteria from spec Section 7 (IT1–IT10).
- **Mock the LLM where possible** for speed, but also include a “smoke test” with a real small model.

## Output Expectations
Every note pushed to Obsidian must:
- Have valid YAML frontmatter with `concepts` as `[[wikilinks]]`.
- Contain exactly one type‑specific block that matches the assigned `content_type`.
- Include all Always‑On sections (`So What?`, `Now What?`, `Simple Explanation`, `Curiosity Questions`).
- Be deterministic: the same URL processed twice must generate identical classification and concepts.

## Prompt to the LLM Agent
The summarization prompt must:
- Embed the full taxonomy and schema.
- Explicitly instruct: “Given the raw content below, classify it into one of the 12 content types, and populate ONLY the fields corresponding to that type. All other type‑specific fields must be null.”
- Demand strict JSON output matching the Pydantic model.

You may extract the exact prompt from the working code after initial implementation, but start with a long, detailed system prompt.

## Getting Started
1. Copy `.env.example` to `.env` and fill with your values.
2. Ensure LMStudio is running with a capable model (Mistral 7B, Llama 3, Qwen2.5).
3. Install the Obsidian Local REST API plugin and create an API key.
4. Run `pip install -r requirements.txt`
5. Execute `python main.py`

## Important Notes
- The Raspberry Pi may be too slow to run both the pipeline and the LLM. If so, run LMStudio on the Macbook and point the Pi’s `.env` to it. Code should support remote LMStudio URLs.
- Content that is paywalled or requires authentication is out of scope; the fetcher should handle 403/401 gracefully and notify the user.
- The Obsidian vault path and API key must be kept secret; never commit `.env`.

The specification (`spec.md`) is the ultimate source of truth. In case of any ambiguity, refer back to it or ask for clarification.
