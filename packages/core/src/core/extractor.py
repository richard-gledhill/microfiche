"""Extracts a Document from a raw source file path."""

from __future__ import annotations

from pathlib import Path

from core.models.document import Document
from core.parsers import parse_document


def extract(path: Path) -> Document:
    """Extract text and metadata from a single supported file."""

    return parse_document(path)
