# Structured Summarisation Pipeline — System Specification v2.0

**Purpose:** Full-stack specification for an autonomous "thinking inbox" that accepts a URL via Telegram, fetches content, generates a richly structured summary using a local LLM, and files the result into an Obsidian vault as a graph‑ready Markdown note.

**Target audience:** A coding agent (or human developer) who will scaffold, build, test, and deploy the entire application.

**Constraints:**

- Development & testing on a Macbook.
- Production deployment on a local Ubuntu Server (Raspberry Pi).
- LLM served locally via **LMStudio** (OpenAI‑compatible API).
- Obsidian vault accessed through the **Local REST API** plugin.
- All network communication remains within the local network (no external API keys required for LLM inference).

---

## 1. Overview & Goals

The pipeline automates the transformation of diverse web content into a **single, universal, structured knowledge note**. Key design goals:

1. **Frictionless capture** – a Telegram message with a URL is the only input.
2. **Intelligent structuring** – content is classified, annotated, and enriched using a local LLM.
3. **Graph‑ready output** – notes include wikilinks, tags, and explicit connection hints for Obsidian's graph view.
4. **Zero‑maintenance** – fully automated after initial setup; no manual indexing or tagging.

---

## 2. Architecture & Data Flow

```
┌───────────┐                                 ┌───────┬─────────┐
│  Telegram  │ ──────────────────────────────> │   Python App     │
│   Client   │ <── confirmation + preview ─── │  (Raspberry Pi)  │
└───────────┘                                 └───────┬─────────┘
                                                      │
                                                      ▼
                                            ┌─────────────────┐
                                            │  Content Fetcher │
                                            │  (trafilatura,   │
                                            │   youtube API)   │
                                            └───────┬─────────┘
                                                    │ raw text / transcript
                                                    ▼
                                            ┌─────────────────┐
                                            │   Pydantic AI    │
                                            │   Agent (local)  │
                                            └───────┬─────────┘
                                                    │ StructuredSummary object
                                                    ▼
                                            ┌─────────────────┐
                                            │  Markdown Render │
                                            │  (Jinja2)        │
                                            └───────┬─────────┘
                                                    │ .md file content
                                                    ▼
                                            ┌─────────────────┐
                                            │ Obsidian Local   │
                                            │ REST API         │
                                            │ (Macbook vault)  │
                                            └─────────────────┘
```

**Network note:** The Raspberry Pi (running the Python app) must be able to reach the Macbook's Obsidian REST API (default `http://<macbook-ip>:27124`). This is typically achieved via local LAN or a Tailscale/WireGuard tunnel.

---

## 3. Component Specifications

### 3.1 Telegram Bot Interface

- **Library:** `python-telegram-bot` (async) or `aiogram`.
- **Functionality:**
  - Listens for messages containing a URL.
  - Validates the URL (must be a valid HTTP/HTTPS link).
  - Sends an acknowledgement ("Processing…") and later replies with:
    - Final note location in vault (`filename.md`)
    - One‑line summary preview.
    - Suggested wikilinks (optional).
- **Error handling:**
  - Invalid URL format → immediate reply with guidance.
  - Fetch failure → reply with error type and retry suggestion.
  - LLM failure → reply with "Generation failed, please retry."
  - Obsidian write failure → reply with "Vault write failed, check connection."

### 3.2 Content Fetcher

- **HTML/Article:** `trafilatura` library for main content extraction.
- **YouTube:** `yt-dlp` for transcripts (prefer `youtube_transcript_api` as fallback).
- **Output:** Raw text (or transcript) passed to the agent. Preserves structure where possible (headings, code blocks, list items).

### 3.3 Pydantic AI Agent (Local)

- **Model:** Any OpenAI‑compatible model served by LMStudio.
- **Client setup:**
  ```python
  from pydantic_ai import Agent

  agent = Agent(
      'openai:llama-3-8b-instruct',
      base_url='http://192.168.1.100:1234/v1',
      system_prompt='...',
      output_type=StructuredSummary
  )
  ```
- **Prompt:** Contains the full content‑type taxonomy (Section 4.1), the schema definition, and explicit instructions to output a valid `StructuredSummary` JSON. The prompt is immutable except for the user's raw text.
- **Fallback:** If the local model fails to return valid JSON, the pipeline retries once with a simplified prompt, then flags the error.

### 3.4 Obsidian Vault Integration

- **Plugin:** [Obsidian Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) must be installed and running in the target vault (on the Macbook).
- **API endpoint:** `POST http://<obsidian-ip>:27124/vault/<vault-name>/<path>/<filename>.md`
- **Authentication:** API key passed as `Authorization: Bearer <key>` header.
- **Directory structure:** Notes are created under `Inbox/` by default.
- **Filename:** `{YYYY-MM-DD}_{slugified-title}.md`

---

## 4. Data Models & Routing

### 4.1 Content Type Taxonomy

```python
from typing import List, Optional
from datetime import date
from enum import Enum

class ContentType(str, Enum):
    TECHNICAL_ANALYSIS = "technical-analysis"
    TUTORIAL = "tutorial"
    HOW_TO_GUIDE = "how-to-guide"
    ESSAY = "essay"
    NEWS_REPORT = "news-report"
    REFERENCE = "reference"
    COMPARISON = "comparison"
    RESEARCH_SUMMARY = "research-summary"
    OPINION_PIECE = "opinion-piece"
    LINK_ROUNDUP = "link-roundup"
    PROJECT_SHOWCASE = "project-showcase"
    TALK_TRANSCRIPT = "talk-transcript"

class RhetoricalStance(str, Enum):
    INFORM = "inform"
    PERSUADE = "persuade"
    INSTRUCT = "instruct"
    PROVOKE = "provoke"
    DOCUMENT = "document"

class SourceType(str, Enum):
    OFFICIAL_ENG_BLOG = "official-engineering-blog"
    PERSONAL_BLOG = "personal-blog"
    SUBSTACK = "substack"
    MEDIUM = "medium"
    DEVTO = "devto"
    NEWS_OUTLET = "news-outlet"
    ACADEMIC = "academic"
    VIDEO_PLATFORM = "video-platform"
    DOCUMENTATION = "documentation"
    SOCIAL_THREAD = "social-thread"
    UNKNOWN = "unknown"

class Difficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
```

### 4.2 StructuredSummary Model

```python
# --- Section models ---
class KeyClaim(BaseModel):
    claim: str
    evidence: str
    interpretation: str

class TutorialStep(BaseModel):
    step: str
    why: str
    code_or_command: Optional[str] = None

class ArgumentPoint(BaseModel):
    claim: str
    reason: str
    objection: Optional[str] = None
    rebuttal: Optional[str] = None

class FiveWOneH(BaseModel):
    who: str
    what: str
    when: str
    where: str
    why: str
    how: str

class ComparisonRow(BaseModel):
    dimension: str
    values: dict[str, str]

class CuratedLink(BaseModel):
    title: str
    url: str
    summary: str

# --- Top-level structured output ---
class StructuredSummary(BaseModel):
    # Frontmatter
    title: str
    source_url: str
    author: Optional[str] = None
    published_date: Optional[date] = None
    consumed_date: date = Field(default_factory=date.today)
    content_type: ContentType
    rhetorical_stance: Optional[RhetoricalStance] = None
    source_type: SourceType
    tags: List[str] = Field(default_factory=list, min_length=2, max_length=5)
    concepts: List[str] = Field(default_factory=list, min_length=1, max_length=8)
    source_domain: str
    word_count: Optional[int] = None

    # Core Synthesis
    one_line_summary: str
    core_question: str

    # Content-type-specific blocks (populated conditionally)
    context: Optional[str] = None
    key_claims: Optional[List[KeyClaim]] = None
    methodology: Optional[str] = None
    limitations: Optional[str] = None

    problem: Optional[str] = None
    prerequisites: Optional[str] = None
    tutorial_steps: Optional[List[TutorialStep]] = None
    gotchas: Optional[str] = None
    end_result: Optional[str] = None

    central_argument: Optional[str] = None
    argument_structure: Optional[List[ArgumentPoint]] = None
    my_response: Optional[str] = None

    what_happened: Optional[FiveWOneH] = None
    why_it_matters: Optional[str] = None
    key_players: Optional[str] = None
    related_stories: Optional[str] = None

    definition: Optional[str] = None
    key_details: Optional[str] = None
    usage_examples: Optional[str] = None

    things_compared: Optional[str] = None
    comparison_dimensions: Optional[List[ComparisonRow]] = None
    recommendation: Optional[str] = None

    curated_links: Optional[List[CuratedLink]] = None

    what_was_built: Optional[str] = None
    tech_stack: Optional[str] = None
    interesting_decisions: Optional[str] = None
    lessons_learned: Optional[str] = None

    speaker_and_venue: Optional[str] = None
    narrative_arc: Optional[str] = None
    memorable_quotes_list: Optional[List[str]] = None

    # Always-On Sections
    so_what: str
    now_what: str
    simple_explanation: str
    curiosity_questions: List[str] = Field(default_factory=list, min_length=2, max_length=5)
    vault_connections: List[str] = Field(default_factory=list)

    # Optional Bonus Fields
    memorable_quotes: Optional[List[str]] = None
    counterarguments: Optional[str] = None
    reading_time_minutes: Optional[int] = None
    difficulty: Optional[Difficulty] = None
    contains_code: bool = False
```

**Validation rules added programmatically:**

- `one_line_summary` ≤ 280 characters.
- `simple_explanation` ≤ 150 words.
- `concepts` must be 1–8 items, Title Case, suitable as `[[wikilinks]]`.
- Content‑type‑specific block matching `content_type` must be fully populated; all others must be `None`.

### 4.3 Content‑Type Routing Logic

The LLM prompt must instruct the model to:

1. **Detect `content_type`** from the taxonomy based on URL, source, and content structure.
2. **Detect `rhetorical_stance` and `source_type`.**
3. **Fill frontmatter** completely.
4. **Populate exactly ONE** content‑type‑specific block (the one matching `content_type`); all other type‑specific blocks must be `None`.
5. **Always populate** the "Always‑On Sections" (`so_what`, `now_what`, `simple_explanation`, `curiosity_questions`, `vault_connections`).
6. **Respect all validation rules** (character limits, list lengths, etc.).

---

## 5. Markdown Renderer

The renderer converts a `StructuredSummary` instance into an Obsidian‑compatible Markdown file with YAML frontmatter.

### Frontmatter

```yaml
---
title: {title}
source_url: {url}
author: {author or null}
published_date: {YYYY-MM-DD or null}
consumed_date: {YYYY-MM-DD}
content_type: {content_type}
source_type: {source_type}
tags: [{tags}]
concepts: [[{concepts}]]
---
```

### Body

All notes share a common structure:

```markdown
# {title}

**{author if present}**

## Summary
{one_line_summary}

## Core Question
{core_question}

## {Content-Type-Specific Section}
{...}

## So What
{so_what}

## Now What
{now_what}

## Simple Explanation
{simple_explanation}

## Curiosity Questions
- {question 1}
- {question 2}

## Vault Connections
{vault_connections}

## Metadata
- Source: [[{source_domain}]]
- Word count: {word_count}
- Reading time: {reading_time_minutes} min
- Contains code: {yes/no}
```

The renderer must handle `None` values gracefully — omit optional sections rather than rendering "null".

---

## 6. Deployment

### 6.1 Raspberry Pi Setup

1. **Install Raspberry Pi OS (64‑bit)** on SD card.
2. **Enable SSH** and set up Wi‑Fi credentials.
3. **Install Python 3.11+** (`sudo apt update && sudo apt install python3.11 python3.11-venv`).
4. **Clone the repository**:
   ```bash
   git clone https://github.com/<your-repo>/knowledge-pipeline.git
   cd knowledge-pipeline
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
5. **Configure `.env`** (see Section 6.2).
6. **Start the bot**: `python main.py` — use `nohup` or `screen` for background operation.
7. **Configure Telegram webhook** (or use polling for dev).

### 6.2 Environment Variables

```bash
# Telegram
TELEGRAM_BOT_TOKEN=<your-token>
TELEGRAM_WEBHOOK_SECRET=<secret>

# LLM (LMStudio)
LMSTUDIO_BASE_URL=http://192.168.1.100:1234/v1
LMSTUDIO_MODEL=llama-3-8b-instruct

# Obsidian Vault
OBSIDIAN_API_KEY=<your-api-key>
OBSIDIAN_BASE_URL=http://192.168.1.200:27124
OBSIDIAN_VAULT_NAME=<vault-name>
```

### 6.3 Production systemd Service

```ini
[Unit]
Description=Knowledge Pipeline Bot
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/knowledge-pipeline
ExecStart=/home/pi/knowledge-pipeline/venv/bin/python main.py
Restart=on-failure
EnvironmentFile=/home/pi/knowledge-pipeline/.env

[Install]
WantedBy=multi-user.target
```

1. Ensure network connectivity between Pi and Obsidian host (Macbook) – Tailscale recommended.

**Performance note:** If the Pi also runs LMStudio, choose a heavily quantised model (e.g., `Q4_K_M`). Inference will be slow; consider offloading to a separate machine for reasonable latency.

---

## 7. Testing & Acceptance Criteria

The coding agent must provide test suites validating the entire pipeline.

### 7.1 Unit Tests

- **Content classification:** Feed excerpts of known types and assert the correct `ContentType` and `RhetoricalStance`.
- **Pydantic model validation:** Create valid `StructuredSummary` instances and ensure they serialise/deserialise correctly, including edge cases (missing optional fields, length limits).
- **Renderer:** Verify that a `StructuredSummary` → Markdown conversion produces valid YAML frontmatter and expected body sections.
- **Vault client:** Mock the REST API and confirm the correct payload is sent for note creation.

### 7.2 Integration Tests

- **End‑to‑end URL → note:** Use a real (or mocked) Telegram message containing a URL and verify:
  1. The fetcher returns non‑empty text.
  2. The agent returns a valid `StructuredSummary`.
  3. The renderer produces a `.md` file.
  4. The vault client receives a `PUT` request with the correct content.
- **Error propagation:** Verify that each failure mode (fetch, LLM, vault) surfaces the correct error message to the user.

### 7.3 Acceptance Criteria

| Scenario | Expected Result |
|---|---|
| User sends a valid URL via Telegram | Note appears in Obsidian `Inbox/` with correct frontmatter and body. |
| Content is a YouTube video | Transcript is extracted and summarised; `source_type` = "video-platform". |
| Content is a technical blog post | `content_type` = "technical-analysis"; tags include relevant concepts. |
| LLM returns invalid JSON | Pipeline retries once; if still failing, user receives "Generation failed" message. |
| Obsidian vault is unreachable | User receives "Vault write failed, check connection." |
| URL is malformed | Immediate user feedback: "Invalid URL format." |

---

## 8. Future Extensions (Out of Scope for v2.0)

- Multi‑vault support (choose destination via Telegram inline keyboard).
- Scheduled batch processing of multiple URLs.
- Automatic backlink updates when existing notes change.
- Embedding‑based semantic search across the vault.
- Voice note input (Telegram audio messages → Whisper transcription).