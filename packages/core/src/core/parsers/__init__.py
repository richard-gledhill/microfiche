"""Dispatches a file path to the right format parser based on its extension."""

from __future__ import annotations

from pathlib import Path

from core.models.document import Document
from core.parsers import docx_parser, eml_parser, markdown_parser, msg_parser, pdf_parser, txt_parser

_PARSERS = {
    ".pdf": pdf_parser.parse,
    ".docx": docx_parser.parse,
    ".txt": txt_parser.parse,
    ".md": markdown_parser.parse,
    ".markdown": markdown_parser.parse,
    ".msg": msg_parser.parse,
    ".eml": eml_parser.parse,
}

SUPPORTED_EXTENSIONS = frozenset(_PARSERS)


def parse_document(path: Path) -> Document:
    """Parse ``path`` with the parser registered for its extension.

    Raises:
        ValueError: if the extension isn't supported.
    """

    parser = _PARSERS.get(path.suffix.lower())
    if parser is None:
        raise ValueError(f"No parser registered for extension '{path.suffix}' ({path})")  # noqa: TRY003
    return parser(path)
