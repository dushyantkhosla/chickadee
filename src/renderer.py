"""Render AnyNote to Obsidian-compatible Markdown."""

import yaml

from src.models import (
    AnyNote,
    ArticleNote,
    EssayNote,
    FieldNote,
    PaperNote,
    RepoNote,
    TalkNote,
)


def render(note: AnyNote) -> str:
    frontmatter = _render_frontmatter(note.meta)
    body = _render_body(note)
    return f"---\n{frontmatter}---\n\n{body}"


def _render_frontmatter(meta) -> str:
    data = {
        "tags": meta.tags,
        "builds_on": [f"[[{t}]]" for t in meta.builds_on],
        "see_also": [f"[[{t}]]" for t in meta.see_also],
        "contradicts": [f"[[{t}]]" for t in meta.contradicts],
        "source_url": str(meta.source_url),
        "source_type": meta.source_type.value,
        "ingested_on": meta.ingested_on.isoformat(),
    }
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _render_body(note: AnyNote) -> str:
    if isinstance(note, TalkNote):
        return _render_talk(note)
    if isinstance(note, ArticleNote):
        return _render_article(note)
    if isinstance(note, PaperNote):
        return _render_paper(note)
    if isinstance(note, EssayNote):
        return _render_essay(note)
    if isinstance(note, RepoNote):
        return _render_repo(note)
    if isinstance(note, FieldNote):
        return _render_field(note)
    raise TypeError(f"Unknown note type: {type(note)}")


def _author_line(note: AnyNote) -> str:
    if isinstance(note, TalkNote):
        venue = f" — {note.venue}" if note.venue else ""
        return f"_{note.speaker}{venue}_"
    if isinstance(note, (ArticleNote, EssayNote, FieldNote)):
        return f"_{note.author}_" if note.author else ""
    if isinstance(note, PaperNote):
        authors = ", ".join(note.authors)
        year = f" ({note.year})" if note.year else ""
        return f"_{authors}{year}_"
    return ""


def _render_talk(note: TalkNote) -> str:
    lines = [f"# {note.title}", ""]
    if note.speaker:
        lines.append(_author_line(note))
        lines.append("")
    lines.append(f"## Summary\n{note.thesis}")
    if note.arguments:
        lines.extend(["", "## Arguments", ""])
        lines.extend(f"- {a}" for a in note.arguments)
    if note.key_quotes:
        lines.extend(["", "## Key quotes", ""])
        lines.extend(f"> {q}" for q in note.key_quotes)
    lines.extend(_render_open_questions(note.open_questions))
    lines.extend(_render_reflection(note.reflection))
    return "\n".join(lines)


def _render_article(note: ArticleNote) -> str:
    lines = [f"# {note.title}", ""]
    if note.author:
        lines.append(_author_line(note))
        lines.append("")
    lines.append(f"## Summary\n{note.thesis}")
    if note.key_points:
        lines.extend(["", "## Key points", ""])
        lines.extend(f"- {p}" for p in note.key_points)
    if note.evidence:
        lines.extend(["", "## Evidence", ""])
        lines.extend(f"- {e}" for e in note.evidence)
    lines.extend(_render_open_questions(note.open_questions))
    lines.extend(_render_reflection(note.reflection))
    return "\n".join(lines)


def _render_paper(note: PaperNote) -> str:
    lines = [f"# {note.title}", ""]
    lines.append(_author_line(note))
    lines.append("")
    lines.append(f"## Summary\n{note.hypothesis}")
    lines.extend(["", "## Methodology", "", note.methodology])
    if note.findings:
        lines.extend(["", "## Findings", ""])
        lines.extend(f"- {f}" for f in note.findings)
    if note.limitations:
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {l}" for l in note.limitations)
    lines.extend(_render_open_questions(note.open_questions))
    lines.extend(_render_reflection(note.reflection))
    return "\n".join(lines)


def _render_essay(note: EssayNote) -> str:
    lines = [f"# {note.title}", ""]
    if note.author:
        lines.append(_author_line(note))
        lines.append("")
    lines.append(f"## Summary\n{note.thesis}")
    if note.claimed:
        lines.extend(["", "## Claimed (unverified)", ""])
        lines.extend(f"- {c}" for c in note.claimed)
    if note.evidenced:
        lines.extend(["", "## Evidenced", ""])
        lines.extend(f"- {e}" for e in note.evidenced)
    lines.extend(_render_open_questions(note.open_questions))
    lines.extend(_render_reflection(note.reflection))
    return "\n".join(lines)


def _render_repo(note: RepoNote) -> str:
    lines = [f"# {note.name}", ""]
    lines.append(f"## Summary\n{note.what_it_does}")
    if note.stack:
        lines.extend(["", "## Stack", ""])
        lines.extend(f"- {s}" for s in note.stack)
    if note.key_patterns:
        lines.extend(["", "## Key patterns", ""])
        lines.extend(f"- {p}" for p in note.key_patterns)
    lines.extend(_render_open_questions(note.open_questions))
    lines.extend(_render_reflection(note.reflection))
    return "\n".join(lines)


def _render_field(note: FieldNote) -> str:
    lines = [f"# {note.title}", ""]
    if note.author:
        lines.append(_author_line(note))
        lines.append("")
    if note.subject:
        lines.append(f"**Subject:** {note.subject}")
        lines.append("")
    lines.append(f"## Summary\n{note.what_changed}")
    if note.data_points:
        lines.extend(["", "## Data points", ""])
        lines.extend(f"- {d}" for d in note.data_points)
    if note.code_snippets:
        lines.extend(["", "## Code", ""])
        for snippet in note.code_snippets:
            lines.extend(["```bash", snippet, "```", ""])
    if note.authors_take:
        lines.append(f"**Author's take:** {note.authors_take}")
    lines.append(f"**Shelf life:** {note.shelf_life.value}")
    lines.extend(_render_open_questions(note.open_questions))
    lines.extend(_render_reflection(note.reflection))
    return "\n".join(lines)


def _render_open_questions(questions: list[str]) -> list[str]:
    if not questions:
        return []
    return ["", "## Open questions", ""] + [f"- {q}" for q in questions]


def _render_reflection(reflection) -> list[str]:
    lines = ["", "## Reflection", ""]
    if reflection.my_take:
        lines.append(f"**My take:** {reflection.my_take}")
    if reflection.so_what:
        lines.append(f"**So what:** {reflection.so_what}")
    if reflection.now_what:
        lines.append(f"**Now what:** {reflection.now_what}")
    return lines
