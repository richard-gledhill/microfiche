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

from microfiche.core.models.document import Document, UnreadableDocument
from microfiche.core.parsers import docx_parser, eml_parser, markdown_parser, msg_parser, pdf_parser, txt_parser
from microfiche.core.parsers.base import Parser
from microfiche.core.utils.errors import describe_error

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

_MEGABYTE = 1024 * 1024


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
    """Whether ``path``'s extension (case-insensitively) has a registered parser.

    Args:
        path: The file to check.

    Returns:
        ``True`` if a parser is registered for the extension.
    """

    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def parse_document(path: Path, *, max_bytes: int | None = None) -> Document:
    """Parse ``path`` with the parser registered for its extension.

    Args:
        path: The file to parse.
        max_bytes: Refuse a file bigger than this, without reading it. ``None`` means no limit.

    Returns:
        The extracted ``Document``.

    Raises:
        UnsupportedFormatError: if no parser is registered for the file's extension.
        UnreadableDocumentError: if the file is over ``max_bytes`` or its parser fails for any reason.
    """

    parser = _PARSERS.get(path.suffix.lower())
    if parser is None:
        raise UnsupportedFormatError(path)
    try:
        size = path.stat().st_size
    except OSError as err:
        raise UnreadableDocumentError(path, describe_error(err)) from err
    if max_bytes is not None and size > max_bytes:
        raise UnreadableDocumentError(
            path,
            f"it is {size / _MEGABYTE:.1f} MB, over the {max_bytes / _MEGABYTE:g} MB limit ([parsing] max_file_mb)",
        )
    try:
        return parser(path)
    except Exception as err:
        raise UnreadableDocumentError(path, describe_error(err)) from err


def read_documents(paths: Iterable[Path], *, max_bytes: int | None = None) -> DocumentsRead:
    """Read every supported file in ``paths``.

    Unsupported files are skipped silently (they are not documents). Supported files that can't
    be read, or are bigger than ``max_bytes``, are collected in ``unreadable`` instead of stopping
    the batch.

    Args:
        paths: The files to read.
        max_bytes: Leave a file bigger than this unread. ``None`` means no limit.

    Returns:
        The documents that were read and the supported files that could not be.
    """

    result = DocumentsRead()
    for path in paths:
        if not is_supported(path):
            continue
        try:
            result.documents.append(parse_document(path, max_bytes=max_bytes))
        except UnreadableDocumentError as err:
            result.unreadable.append(UnreadableDocument(file_path=path, reason=err.reason))
    return result
