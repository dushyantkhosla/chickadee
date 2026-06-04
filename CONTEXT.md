# Chickadee

Telegram bot that ingests URLs, fetches content, summarises with LLM, and writes structured notes to a vault (Obsidian or Logseq).

## Language

**Vault**:
The directory where Chickadee writes rendered notes. Can be an Obsidian vault or a Logseq graph depending on the `VAULT_BACKEND` setting.
_Avoid_: notebook, database, store

**Note**:
A single ingested URL rendered as a structured Markdown file with metadata (tags, source URL, links to other notes). One of six types: TalkNote, ArticleNote, PaperNote, EssayNote, RepoNote, FieldNote.
_AVOID_: entry, post, document

**VaultMetadata**:
The shared metadata model embedded in every note type. Contains tags, link fields (builds_on, see_also, contradicts), source URL, source type, and ingestion date. Rendered as YAML frontmatter in Obsidian mode or `property:: value` lines in Logseq mode.
_Avoid_: ObsidianMetadata, Frontmatter, Meta

**Backend**:
The vault format variant selected via `VAULT_BACKEND` env var. Either `obsidian` or `logseq`. Determines metadata format, file naming, and directory structure.
_Avoid_: mode, format, type

**Link grounding**:
The process of populating builds_on, see_also, and contradicts fields by matching against existing vault note titles. Prevents the LLM from inventing note titles.
_Avoid_: backlinking, cross-referencing

**Provider chain**:
The 3-tier LLM fallback system: LM Studio (local) → Vercel AI Gateway (paid) → free pool. Tries each in order, returns first success.
_Avoid_: fallback chain, LLM rotation
