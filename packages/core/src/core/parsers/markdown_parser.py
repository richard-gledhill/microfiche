"""Parses Markdown files.

Currently identical to the plain text parser; kept separate so front-matter/heading-aware
extraction can be added later without touching txt_parser.
"""

from __future__ import annotations

from pathlib import Path

from core.models.document import Document


def parse(path: Path) -> Document:
    content = path.read_text(encoding="utf-8", errors="replace")
    return Document(file_path=path, file_name=path.name, extension=path.suffix.lower(), content=content)
