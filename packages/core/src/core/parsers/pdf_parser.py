"""Parses PDF documents via PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from core.models.document import Document
from core.parsers.base import document_from


def parse(path: Path) -> Document:
    with pymupdf.open(path) as pdf:
        text = "\n".join(page.get_text() for page in pdf)
        metadata = {str(key): str(value) for key, value in (pdf.metadata or {}).items() if value}
    return document_from(path, text, metadata)
