"""Common parser interface: every format parser turns a file path into a Document."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from core.models.document import Document


class Parser(Protocol):
    def __call__(self, path: Path) -> Document: ...


def document_from(path: Path, content: str, metadata: dict[str, str] | None = None) -> Document:
    """Build the ``Document`` for ``path`` from what a format parser extracted.

    Fills in the fields every parser would otherwise repeat: the path, its file name, and its
    lowercased extension.
    """

    return Document(
        file_path=path,
        file_name=path.name,
        extension=path.suffix.lower(),
        content=content,
        metadata=metadata or {},
    )
