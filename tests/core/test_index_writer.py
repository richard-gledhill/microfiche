"""Tests for Obsidian index.md generation."""

from datetime import date
from pathlib import Path

from core.obsidian.index_writer import IndexEntry, write_index


def test_write_index_links_markdown_and_other_files(tmp_path: Path) -> None:
    entries = [
        IndexEntry(file_name="notes.md", tags=["requirements"], confidence=0.9, filed_on=date(2026, 9, 7)),
        IndexEntry(file_name="spec.pdf", tags=["architecture"], confidence=0.8, filed_on=date(2026, 9, 7)),
    ]

    index_path = write_index(tmp_path, entries)
    content = index_path.read_text(encoding="utf-8")

    assert "[[notes]]" in content
    assert "[spec](spec.pdf)" in content
