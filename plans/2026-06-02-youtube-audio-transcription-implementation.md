# Implementation Plan: YouTube Audio Transcription

**Spec:** `plans/2026-06-02-youtube-audio-transcription.md`
**Date:** 2026-06-02

## Step 1: Schema changes — `models.py`

**Files:** `src/models.py`

1. Add `upload_date: Optional[date] = None` to `ObsidianMetadata`
2. Remove `venue` from `TalkNote`
3. Add `YouTubeMetadata` dataclass:
   ```python
   from dataclasses import dataclass, field

   @dataclass
   class YouTubeMetadata:
       title: str
       channel: str
       upload_date: Optional[str] = None
       view_count: Optional[int] = None
       like_count: Optional[int] = None
       channel_follower_count: Optional[int] = None
       categories: list[str] = field(default_factory=list)
   ```

**Verification:** Run `pytest tests/test_models.py` — update any tests that reference `venue`.

---

## Step 2: Create transcriber module — `transcriber.py`

**Files:** `src/transcriber.py` (new)

Create sync module with three functions adapted from the dk-transcribe-summarize skill:

1. `download_audio(url: str) -> tuple[Path, YouTubeMetadata]`
   - Adapt from `scripts/audio.py:download_audio()`
   - Use `yt_dlp.YoutubeDL` with Brave cookies, Node.js, ffmpeg post-processing
   - Extract metadata into `YouTubeMetadata`
   - Wrap `DownloadError` in `FetchError`

2. `transcribe_audio(audio_path: Path) -> str`
   - Adapt from `scripts/llm.py:transcribe()` + `openrouter_chat()`
   - Compress if > 6MB via ffmpeg subprocess
   - Send base64 audio to OpenRouter `xiaomi/mimo-v2.5`
   - Return transcription text
   - Wrap API errors in `FetchError`, empty result in `ParseError`

3. `fetch_youtube_transcript(url: str) -> tuple[str, YouTubeMetadata]`
   - Orchestrate: download → transcribe → cleanup temp files
   - Use `finally` block for cleanup (matching skill pattern)

**Verification:** Write `tests/test_transcriber.py` with mocks for yt_dlp, requests, subprocess. Run `pytest tests/test_transcriber.py`.

---

## Step 3: Update fetcher — `fetcher.py`

**Files:** `src/fetcher.py`

1. Remove `youtube_transcript_api` import and `_fetch_transcript()` function
2. Remove `_extract_youtube_video_id()` function
3. Change `fetch()` signature: `async def fetch(url: str) -> tuple[str, Optional[YouTubeMetadata]]`
4. YouTube path: call `await asyncio.to_thread(transcriber.fetch_youtube_transcript, url)`
5. HTML path: return `(text, None)`

**Verification:** Update `tests/test_fetcher.py`:
- Replace `YouTubeTranscriptApi` mocks with `transcriber.fetch_youtube_transcript` mocks
- Update return type assertions for tuple
- Run `pytest tests/test_fetcher.py`

---

## Step 4: Update agent — `agent.py`

**Files:** `src/agent.py`

1. Add `TalkMetadata` dataclass:
   ```python
   @dataclass
   class TalkMetadata:
       title: str
       speaker: str
       categories: list[str]
       upload_date: Optional[date]
   ```

2. Update `summarise()` to accept optional `deps` parameter:
   ```python
   async def summarise(
       text: str,
       content_type: ContentType,
       vault_titles: list[str],
       url: str,
       deps: Any = None,  # NEW
   ) -> AnyNote:
   ```

3. When `content_type == ContentType.talk` and `deps` is `TalkMetadata`:
   - Create agent with `deps_type=TalkMetadata`
   - Add `@agent.instructions` that injects title, speaker, categories into prompt
   - Prompt no longer asks LLM to produce title/speaker

4. Simplify `_build_summariser_prompt()` for talk type:
   - Remove "determine the title" language
   - Remove "identify the speaker" language
   - Add: "Title and speaker are provided via context. Focus on: thesis, arguments, key_quotes."

**Verification:** Update `tests/test_agent.py`:
- Add test for `summarise()` with `TalkMetadata` deps
- Verify simplified prompt doesn't ask for title/speaker
- Run `pytest tests/test_agent.py`

---

## Step 5: Update pipeline — `main.py`

**Files:** `src/main.py`

1. Update `run_pipeline()` to handle new `fetch()` return type:
   ```python
   text, yt_metadata = await fetch(url)
   ```

2. For YouTube (`yt_metadata is not None`):
   - Create `TalkMetadata` from yt_metadata
   - Pre-populate: title, speaker (from channel), upload_date (parsed from YYYYMMDD)
   - Pass to `summarise(..., deps=talk_metadata)`

3. For HTML (`yt_metadata is None`): unchanged, `deps=None`

4. Parse `upload_date` from yt-dlp format (YYYYMMDD) to `date` object

**Verification:** Update `tests/test_main.py`:
- Mock `fetch()` returning `(text, YouTubeMetadata(...))`
- Verify `TalkMetadata` is created and passed to `summarise()`
- Run `pytest tests/test_main.py`

---

## Step 6: Update renderer — `renderer.py`

**Files:** `src/renderer.py`

1. `_render_talk()`: remove venue from author line
   - Before: `_{speaker} — {venue}_`
   - After: `_{speaker}_`

2. `_render_frontmatter()`: add `upload_date` field
   - If `upload_date` is not None: render `upload_date: YYYY-MM-DD`
   - If None: omit from frontmatter

**Verification:** Update `tests/test_renderer.py`:
- Update talk rendering tests (no venue)
- Add test for frontmatter with upload_date
- Add test for frontmatter without upload_date
- Run `pytest tests/test_renderer.py`

---

## Step 7: Update dependencies

**Files:** `pyproject.toml`, `.env.example`

1. `pyproject.toml`:
   - Add: `"yt-dlp>=2025.0"`
   - Remove: `"youtube-transcript-api>=1.0"`

2. `.env.example`:
   - Add: `OPENROUTER_API_KEY=`

3. `Dockerfile` (if exists):
   - Ensure `ffmpeg`, `yt-dlp`, `node`, Brave browser are installed
   - Document in README

**Verification:** Run `uv lock` to regenerate lockfile. Run full test suite `pytest`.

---

## Step 8: Cleanup and final verification

1. Remove `youtube_transcript_api` from `pyproject.toml` dependencies
2. Remove any dead code referencing the old transcript API
3. Run full test suite: `pytest`
4. Run linter/typecheck if configured
5. Manual test: `python -m src.main "https://www.youtube.com/watch?v=VIDEO_ID"` with a short video
6. Manual test: bot receives YouTube URL, processes async, sends confirmation

---

## Implementation order

```
Step 1 (models)  ← no dependencies
Step 2 (transcriber)  ← no dependencies (can parallel with Step 1)
Step 3 (fetcher)  ← depends on Steps 1 + 2
Step 4 (agent)  ← depends on Step 1
Step 5 (main)  ← depends on Steps 3 + 4
Step 6 (renderer)  ← depends on Step 1
Step 7 (deps)  ← depends on Step 2
Step 8 (cleanup)  ← depends on all above
```

Steps 1, 2, 6, 7 can be done in parallel. Steps 3, 4 depend on 1+2. Step 5 depends on 3+4. Step 8 is final.

---

## Risk areas

1. **yt-dlp cookie handling** — Brave cookies may not be available in all environments. Containerized deployment needs Brave installed.
2. **Audio size limits** — Long videos produce large audio files. The 6MB compression threshold from the skill should be validated.
3. **OpenRouter rate limits** — If processing many YouTube URLs in sequence, may hit rate limits. Add retry logic (skill already has 5-attempt retry).
4. **Temp file cleanup** — If transcribe crashes after download, temp audio files linger. The `finally` block in `fetch_youtube_transcript` handles this.
