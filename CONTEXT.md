# Chickadee — Domain Language

## Core concepts

| Term | Definition |
|------|-----------|
| **ContentType** | Enum of six note types: talk, article, paper, essay, repo, field. Determines which Pydantic model is used. |
| **\*Note** | Any of the six Pydantic model types (TalkNote, ArticleNote, etc.) |
| **AnyNote** | Union type: `TalkNote \| ArticleNote \| PaperNote \| EssayNote \| RepoNote \| FieldNote` |
| **Link fields** | `builds_on`, `see_also`, `contradicts` in ObsidianMetadata — wikilink references to other vault notes |
| **Inbox/** | Triage folder where all new notes land; Obsidian graph forms naturally |
| **Reflection** | Personal interpretation block: `my_take`, `so_what`, `now_what` |
| **IEI spine** | TalkNote.arguments structure: Introduction, Evidence, Implications |
| **shelf_life** | FieldNote-specific: how long the information stays relevant (days/months/evergreen) |
| **Two-tier routing** | Tier 1: domain lookup in UNAMBIGUOUS_DOMAINS. Tier 2: LLM classification for unknown/multi-type domains |
| **Link grounding** | Populating link fields using exact vault note titles passed in the system prompt |

## Fetching strategies (current)

| Term | Definition |
|------|-----------|
| **Transcript API** | Current approach: `youtube_transcript_api` library fetches subtitle text directly from YouTube |
| **HTML fetch** | Current approach: `httpx` + `trafilatura` extracts text from web articles |
| **Audio download** | Proposed approach: `yt-dlp` downloads audio, then LLM transcribes (from dk-transcribe-summarize skill) |
| **Multimodal transcription** | Proposed: send audio as base64 data URI to a multimodal LLM API for transcription |

## Pipeline stages

| Term | Definition |
|------|-----------|
| **Fetch** | `fetcher.py` — get raw text from URL (transcript API or HTML) |
| **Route** | `router.py` — determine ContentType from domain |
| **Classify** | `agent.py` — LLM fallback when domain is ambiguous |
| **Summarise** | `agent.py` — PydanticAI agent produces typed *Note from text |
| **Render** | `renderer.py` — *Note → Markdown with YAML frontmatter |
| **Write** | `vault.py` — save .md to Obsidian vault Inbox/ |

## External services

| Service | Current usage | Proposed change |
|---------|--------------|-----------------|
| LM Studio (local) | Classification + summarisation | Unchanged |
| OpenRouter | Not used | Transcription (new) |
| YouTube Transcript API | Transcript fetch | Removed (replaced by yt-dlp + transcription) |
| yt-dlp | Not used | Audio download (new) |
