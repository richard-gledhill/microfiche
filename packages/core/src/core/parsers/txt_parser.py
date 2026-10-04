"""Parses plain text files."""

from __future__ import annotations

from pathlib import Path

from core.models.document import Document
from core.parsers.base import document_from


def parse(path: Path) -> Document:
    return document_from(path, path.read_text(encoding="utf-8", errors="replace"))
