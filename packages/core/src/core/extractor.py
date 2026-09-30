"""Extracts a Document from a raw source file path."""

from __future__ import annotations

from pathlib import Path

from core.models.document import Document
from core.parsers import parse_document


def extract(path: Path) -> Document:
    """
    Extracts text and metadata and parses a document from the specified single supported file.

    This function reads a file from the given path, processes its content,
    and returns a `Document` object based on the parsed data.

    Args:
        path (Path): The file path to extract and parse the document from.

    Returns:
        Document: The parsed document object.
    Todo:
        - review this module. Seems like it could be combined with the parser module.
    """

    return parse_document(path)
