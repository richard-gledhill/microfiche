"""Generates/refreshes an Obsidian-friendly index.md (folder note) for a category folder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass
class IndexEntry:
    """One filed document, as it should appear in its folder's index.md.

    Attributes:
        file_name: The document's file name.
        tags: The tags to list against it.
        confidence: The confidence it was filed with.
        filed_on: The date it was filed.
    """

    file_name: str
    tags: list[str]
    confidence: float
    filed_on: date


def write_index(folder: Path, entries: list[IndexEntry]) -> Path:
    """Write ``folder/index.md`` listing every entry.

    Uses ``[[wikilinks]]`` for Markdown notes and relative ``[title](file)`` links for
    everything else (PDF, DOCX, ...), matching normal Obsidian convention. Regenerated in
    full each time it's called, so it always reflects the folder's current contents.

    Args:
        folder: The category folder to write the index into.
        entries: The documents to list.

    Returns:
        The path of the written ``index.md``.
    """

    lines = [f"# {folder.name}", ""]
    for entry in sorted(entries, key=lambda e: e.file_name.lower()):
        stem = Path(entry.file_name).stem
        link = f"[[{stem}]]" if entry.file_name.lower().endswith(".md") else f"[{stem}]({entry.file_name})"
        tags = " ".join(f"#{tag}" for tag in entry.tags)
        lines.append(f"- {link} — {tags} (filed {entry.filed_on.isoformat()}, confidence {entry.confidence:.2f})")

    index_path = folder / "index.md"
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return index_path
