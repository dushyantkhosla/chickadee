# Spec: YouTube Audio Transcription via yt-dlp + OpenRouter

**Date:** 2026-06-02
**Status:** Draft — awaiting review

## Problem

Chickadee's YouTube flow currently uses `youtube_transcript_api` to fetch subtitle text directly. This fails silently when:
- Videos have no subtitles (many talks, music, non-English content)
- Subtitles are auto-generated and low quality
- YouTube rate-limits or blocks the transcript API

The result: many YouTube URLs produce `ParseError("No transcript available")` and the user gets nothing.

## Goal

Replace the transcript API with an audio-download → LLM-transcription flow:
1. `yt-dlp` downloads audio from YouTube
2. OpenRouter's `xiaomi/mimo-v2.5` (multimodal) transcribes the audio
3. Chickadee's existing summarisation pipeline produces the TalkNote

This works for **any** YouTube video — no subtitle dependency.

## Non-goals

- Changing the summarisation pipeline (PydanticAI agent → TalkNote → Markdown)
- Changing other content types (article, paper, essay, repo, field)
- Progress messages in Telegram (typing indicator is sufficient)

---

## Decisions made

| Decision | Choice | Rationale |
|---|---|---|
| Transcription provider | OpenRouter `xiaomi/mimo-v2.5` | Proven in dk-transcribe-summarize skill, ~$0.004/video |
| System dependencies | Require ffmpeg, yt-dlp, Brave cookies, Node.js | Containerized deployment bundles all deps |
| Fallback to transcript API | None — clean break | `youtube-transcript-api` is unreliable |
| Async bridging | Sync module `src/transcriber.py` + `asyncio.to_thread()` | Minimal refactor, keeps skill code portable |
| Metadata passing | PydanticAI `deps_type` | Idiomatic, LLM sees metadata but doesn't produce it |
| Speaker field | Pre-populate from yt-dlp `channel` | More accurate than LLM guessing |
| Venue field | Drop from TalkNote | YouTube has no venue concept |
| upload_date | New field in `ObsidianMetadata` | General concept, all note types benefit |
| Error handling | Pass through raw yt-dlp/OpenRouter messages | Already human-readable |
| Bot UX | Non-blocking async (already implemented) | User can paste next URL immediately |
| Tests | Mock at boundary, no YouTube integration tests | Consistent with existing patterns |

---

## Schema changes

### `ObsidianMetadata` — add `upload_date`

```python
class ObsidianMetadata(BaseModel):
    tags: list[str] = []
    builds_on: list[str] = []
    see_also: list[str] = []
    contradicts: list[str] = []
    source_url: HttpUrl
    source_type: ContentType
    ingested_on: date
    upload_date: Optional[date] = None  # NEW — publication date from source
```

### `TalkNote` — remove `venue`, speaker from metadata

```python
class TalkNote(BaseModel):
    meta: ObsidianMetadata
    title: str                        # pre-populated from yt-dlp
    speaker: str                      # pre-populated from yt-dlp channel
    # venue: REMOVED
    thesis: str                       # LLM produces this
    arguments: list[str]              # LLM produces this
    key_quotes: list[str]             # LLM produces this
    open_questions: list[str]         # LLM produces this
    reflection: Optional[Reflection] = None
```

### New dataclass — `YouTubeMetadata`

```python
@dataclass
class YouTubeMetadata:
    title: str
    channel: str
    upload_date: Optional[str] = None   # YYYYMMDD from yt-dlp
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    channel_follower_count: Optional[int] = None
    categories: list[str] = field(default_factory=list)
```

---

## New module: `src/transcriber.py`

Sync module. Three public functions:

### `download_audio(url: str) -> tuple[Path, YouTubeMetadata]`

Wraps `yt_dlp.YoutubeDL`:
- Downloads best audio, extracts to m4a via ffmpeg
- Uses Brave cookies (`cookiesfrombrowser: ("brave",)`)
- Uses Node.js for n-challenge solving (`js_runtimes: {"node": {}}`)
- Returns audio file path + `YouTubeMetadata` from `info` dict
- Raises `FetchError` on `yt_dlp.utils.DownloadError`

### `transcribe_audio(audio_path: Path) -> str`

Wraps OpenRouter multimodal API:
- Compresses audio if > 6MB (ffmpeg re-encode to 8kbps mono MP3)
- Encodes as base64 data URI
- Sends to `xiaomi/mimo-v2.5` on OpenRouter
- Returns transcription text
- Raises `ParseError` on empty transcription, `FetchError` on API errors

### `fetch_youtube_transcript(url: str) -> tuple[str, YouTubeMetadata]`

Orchestrator: calls `download_audio` then `transcribe_audio`. Returns (transcript_text, metadata). Cleans up temp files in `finally` block.

---

## Changes to existing modules

### `src/fetcher.py`

- Remove `youtube_transcript_api` import and `_fetch_transcript()` function
- Remove `_extract_youtube_video_id()` (no longer needed)
- YouTube path in `fetch()` now calls `transcriber.fetch_youtube_transcript(url)`
- **Signature change**: `fetch()` returns `tuple[str, Optional[YouTubeMetadata]]` instead of `str`
  - For YouTube: returns `(transcript, metadata)`
  - For HTML: returns `(text, None)`
  - This keeps the caller responsible for handling metadata

### `src/agent.py`

- New `deps_type` dataclass `TalkMetadata`:
  ```python
  @dataclass
  class TalkMetadata:
      title: str
      speaker: str
      categories: list[str]
      upload_date: Optional[date]
  ```
- `summarise()` for `ContentType.talk`: pass `deps=TalkMetadata(...)` to agent
- `_build_summariser_prompt()` for talk type: simplified prompt, no need to ask LLM for title/speaker
- LLM output is now only: thesis, arguments, key_quotes, open_questions, reflection

### `src/main.py`

- `run_pipeline()` handles new `fetch()` return type
- For YouTube: extract metadata, pre-populate TalkNote fields, pass deps to summariser
- For other types: unchanged

### `src/renderer.py`

- `_render_talk()`: remove venue from author line
- `_render_frontmatter()`: add `upload_date` field
- Frontmatter template adds: `upload_date: YYYY-MM-DD` (if present)

### `src/bot.py`

- No structural changes (async deque pattern stays)
- `format_confirmation()`: no changes needed

---

## Renderer changes

### Frontmatter — add upload_date

```yaml
---
tags: [tag-one, tag-two]
builds_on: ["[[Note A]]"]
see_also: ["[[Note B]]"]
contradicts: []
source_url: https://...
source_type: talk
ingested_on: 2026-06-02
upload_date: 2026-05-15        # NEW — only if present
---
```

### Talk author line — remove venue

Before: `_{speaker} — {venue}_`
After: `_{speaker}_`

---

## Dependency changes

### `pyproject.toml`

Add:
```
"yt-dlp>=2025.0",
```

Remove:
```
"youtube-transcript-api>=1.0",
```

### Environment variables (`.env`)

Add:
```
OPENROUTER_API_KEY=            # Required for YouTube transcription
```

### System dependencies (Dockerfile)

Must be present in container:
- `ffmpeg` — audio post-processing
- `yt-dlp` — YouTube audio download
- Brave browser — YouTube cookies (for auth)
- Node.js — yt-dlp n-challenge solving

---

## Test plan

### `tests/test_transcriber.py` (new)

| Test | Mock boundary |
|---|---|
| `test_download_audio_success` | `yt_dlp.YoutubeDL.extract_info` returns mock info dict, mock m4a file on disk |
| `test_download_audio_failure` | `yt_dlp.YoutubeDL.extract_info` raises `DownloadError` → `FetchError` |
| `test_transcribe_audio_success` | `requests.post` returns mock OpenRouter response with transcription text |
| `test_transcribe_audio_large_file` | `subprocess.run` for ffmpeg compression, then OpenRouter call |
| `test_transcribe_audio_empty` | OpenRouter returns empty → `ParseError` |
| `test_fetch_youtube_transcript_orchestration` | Both mocks, verifies cleanup of temp files |

### `tests/test_fetcher.py` — update

| Test | Change |
|---|---|
| `test_fetch_youtube_success` | Replace `YouTubeTranscriptApi` mock with `transcriber.fetch_youtube_transcript` mock |
| `test_fetch_youtube_no_transcript` | Replace with `FetchError` from yt-dlp |
| Return type assertions | Update for `tuple[str, Optional[YouTubeMetadata]]` |

### `tests/test_agent.py` — update

| Test | Change |
|---|---|
| `test_summarise_talk` | Pass `TalkMetadata` deps, verify simplified prompt |

### `tests/test_renderer.py` — update

| Test | Change |
|---|---|
| `test_render_talk` | Remove venue from expected output |
| `test_render_frontmatter_with_upload_date` | Add upload_date assertion |
| `test_render_frontmatter_without_upload_date` | Verify upload_date omitted when None |

### `tests/test_main.py` — update

| Test | Change |
|---|---|
| `test_run_pipeline_youtube` | Mock returns metadata, verify pre-population |

---

## Open questions

1. **Audio compression threshold**: The skill compresses when base64 > 6MB. Should we keep this threshold or adjust?
2. **Transcription model**: Fixed to `xiaomi/mimo-v2.5` or configurable via env var?
3. **Title slugification**: yt-dlp title often differs from what the LLM would produce. Should slug come from yt-dlp title or LLM-inferred title? (They should match since LLM gets title as context.)

---

## Success criteria

1. YouTube URL → audio download → transcription → TalkNote → Obsidian note (end-to-end)
2. TalkNote.title and TalkNote.speaker match yt-dlp metadata
3. No dependency on `youtube_transcript_api`
4. All existing tests pass (updated for new signatures)
5. New tests cover transcriber module at the boundary
6. Bot remains non-blocking — user can paste next URL during processing
