"""Parses .eml email messages using the Python standard library (no extra dependency needed)."""

from __future__ import annotations

from email import policy
from email.parser import BytesParser
from pathlib import Path

from core.models.document import Document
from core.parsers.base import document_from


def parse(path: Path) -> Document:
    """Extract the body, and sender/recipient/subject/date metadata, of an .eml message.

    Args:
        path: The file to parse.

    Returns:
        The extracted ``Document``.
    """

    with path.open("rb") as fh:
        message = BytesParser(policy=policy.default).parse(fh)

    body = message.get_body(preferencelist=("plain", "html"))
    content = body.get_content() if body is not None else ""
    metadata = {
        "sender": message.get("From", ""),
        "to": message.get("To", ""),
        "subject": message.get("Subject", ""),
        "date": message.get("Date", ""),
    }
    return document_from(path, content, metadata)
