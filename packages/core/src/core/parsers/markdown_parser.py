"""Parses Markdown files.

Currently identical to the plain text parser; kept separate so front-matter/heading-aware
extraction can be added later without touching txt_parser.
"""

from __future__ import annotations

from pathlib import Path

from core.models.document import Document
from core.parsers.base import document_from


def parse(path: Path) -> Document:
    return document_from(path, path.read_text(encoding="utf-8", errors="replace"))
