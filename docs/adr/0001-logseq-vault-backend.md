# Logseq vault backend

Chickadee supports two vault backends — Obsidian (YAML frontmatter, `Inbox/` directory) and Logseq (`property:: value` syntax, `pages/` directory). Selected via `VAULT_FORMAT` env var. Default is Obsidian for backward compatibility.

The vault layer is thin (~250 lines across 3 files) and the only difference is metadata format. LLM prompts, agent logic, body rendering, and all other pipeline code is backend-agnostic. A single codebase with conditional rendering is simpler than maintaining two forks.

ObsidianMetadata was renamed to VaultMetadata to reflect backend independence.
