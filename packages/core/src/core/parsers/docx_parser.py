"""Parses Microsoft Word documents via python-docx."""

from __future__ import annotations

from pathlib import Path

import docx

from core.models.document import Document


def parse(path: Path) -> Document:
    document = docx.Document(str(path))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    return Document(file_path=path, file_name=path.name, extension=path.suffix.lower(), content=text)
