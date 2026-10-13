"""Parses plain text files."""

from __future__ import annotations

from pathlib import Path

from microfiche.core.models.document import Document
from microfiche.core.parsers.base import document_from


def parse(path: Path) -> Document:
    """Read a plain text file.

    Args:
        path: The file to parse.

    Returns:
        The extracted ``Document``.
    """

    return document_from(path, path.read_text(encoding="utf-8", errors="replace"))
