"""Parses Microsoft Word documents via python-docx."""

from __future__ import annotations

from pathlib import Path

import docx

from core.models.document import Document
from core.parsers.base import document_from


def parse(path: Path) -> Document:
    """Extract the text of a Word document's paragraphs.

    Args:
        path: The file to parse.

    Returns:
        The extracted ``Document``.
    """

    document = docx.Document(str(path))
    return document_from(path, "\n".join(paragraph.text for paragraph in document.paragraphs))
