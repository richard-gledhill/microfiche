"""Parses PDF documents via PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from core.models.document import Document


def parse(path: Path) -> Document:
    with pymupdf.open(path) as pdf:
        text = "\n".join(page.get_text() for page in pdf)
        metadata = {str(key): str(value) for key, value in (pdf.metadata or {}).items() if value}
    return Document(
        file_path=path,
        file_name=path.name,
        extension=path.suffix.lower(),
        content=text,
        metadata=metadata,
    )
