"""Turns a file into a Document by dispatching to the parser registered for its extension.

This is the one place that knows which formats are supported, and what happens when a file
can't be read: a parser failure never escapes as a raw library exception. ``parse_document``
raises a documented error; ``read_documents`` collects the failures so a caller can carry on
with the files that did read.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from core.models.document import Document, UnreadableDocument
from core.parsers import docx_parser, eml_parser, markdown_parser, msg_parser, pdf_parser, txt_parser
from core.parsers.base import Parser

# Todo: Add support for folder parsing with a collection of documents that sorts the whole folder as a unit.

_PARSERS: dict[str, Parser] = {
    ".pdf": pdf_parser.parse,
    ".docx": docx_parser.parse,
    ".txt": txt_parser.parse,
    ".md": markdown_parser.parse,
    ".markdown": markdown_parser.parse,
    ".msg": msg_parser.parse,
    ".eml": eml_parser.parse,
}

SUPPORTED_EXTENSIONS = frozenset(_PARSERS)

_MAX_REASON_CHARS = 200


class UnsupportedFormatError(ValueError):
    """Raised when asked to parse a file whose extension has no registered parser."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"No parser registered for extension '{path.suffix}' ({path})")


class UnreadableDocumentError(Exception):
    """Raised when a supported file can't be read - corrupt, truncated, password-protected, ....

    Parsers use third-party libraries that share no exception base, so any failure inside one
    is wrapped here; the original exception is kept as ``__cause__``.

    Attributes:
        path: The file that couldn't be read.
        reason: A one-line description of what went wrong.
    """

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Could not read '{path.name}': {reason}")


@dataclass
class DocumentsRead:
    """The outcome of reading a batch of files.

    Attributes:
        documents: The files that were read, in the order given.
        unreadable: The supported files that could not be read, with why.
    """

    documents: list[Document] = field(default_factory=list)
    unreadable: list[UnreadableDocument] = field(default_factory=list)


def is_supported(path: Path) -> bool:
    """Whether ``path``'s extension (case-insensitively) has a registered parser."""

    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def parse_document(path: Path) -> Document:
    """Parse ``path`` with the parser registered for its extension.

    Raises:
        UnsupportedFormatError: if no parser is registered for the file's extension.
        UnreadableDocumentError: if the file's parser fails for any reason.
    """

    parser = _PARSERS.get(path.suffix.lower())
    if parser is None:
        raise UnsupportedFormatError(path)
    try:
        return parser(path)
    except Exception as err:
        raise UnreadableDocumentError(path, _describe(err)) from err


def read_documents(paths: Iterable[Path]) -> DocumentsRead:
    """Read every supported file in ``paths``.

    Unsupported files are skipped silently (they are not documents). Supported files that can't
    be read are collected in ``unreadable`` instead of stopping the batch.
    """

    result = DocumentsRead()
    for path in paths:
        if not is_supported(path):
            continue
        try:
            result.documents.append(parse_document(path))
        except UnreadableDocumentError as err:
            result.unreadable.append(UnreadableDocument(file_path=path, reason=err.reason))
    return result


def _describe(err: Exception) -> str:
    """``ExceptionType: first line of its message``, capped so one bad file can't flood the output."""

    lines = str(err).splitlines()
    text = f"{type(err).__name__}: {lines[0]}" if lines else type(err).__name__
    return text if len(text) <= _MAX_REASON_CHARS else text[: _MAX_REASON_CHARS - 1] + "…"
