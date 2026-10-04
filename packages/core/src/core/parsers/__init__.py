"""Document parsing: reads a file into a Document, whatever its format.

The public interface is re-exported from ``core.parsers.registry``; each ``*_parser`` module is a
format adapter behind it.
"""

from core.parsers.registry import (
    SUPPORTED_EXTENSIONS,
    DocumentsRead,
    UnreadableDocumentError,
    UnsupportedFormatError,
    is_supported,
    parse_document,
    read_documents,
)

__all__ = [
    "SUPPORTED_EXTENSIONS",
    "DocumentsRead",
    "UnreadableDocumentError",
    "UnsupportedFormatError",
    "is_supported",
    "parse_document",
    "read_documents",
]
