"""Parses plain text files."""

from __future__ import annotations

from pathlib import Path

from core.models.document import Document


def parse(path: Path) -> Document:
    content = path.read_text(encoding="utf-8", errors="replace")
    return Document(file_path=path, file_name=path.name, extension=path.suffix.lower(), content=content)
