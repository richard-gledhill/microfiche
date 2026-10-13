"""Common parser interface: every format parser turns a file path into a Document."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from microfiche.core.models.document import Document


class Parser(Protocol):
    """A format parser: turns a file path into a ``Document``."""

    def __call__(self, path: Path) -> Document:
        """Parse the file at ``path``.

        Args:
            path: The file to parse.

        Returns:
            The extracted ``Document``.
        """

        ...


def document_from(path: Path, content: str, metadata: dict[str, str] | None = None) -> Document:
    """Build the ``Document`` for ``path`` from what a format parser extracted.

    Fills in the fields every parser would otherwise repeat: the path, its file name, and its
    lowercased extension.

    Args:
        path: The file that was parsed.
        content: The text the parser extracted.
        metadata: Any format-specific metadata the parser extracted.

    Returns:
        The ``Document`` for ``path``.
    """

    return Document(
        file_path=path,
        file_name=path.name,
        extension=path.suffix.lower(),
        content=content,
        metadata=metadata or {},
    )
