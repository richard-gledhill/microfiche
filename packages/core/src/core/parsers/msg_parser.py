"""Parses Outlook .msg email messages via extract-msg."""

from __future__ import annotations

from pathlib import Path

import extract_msg

from core.models.document import Document
from core.parsers.base import document_from


def parse(path: Path) -> Document:
    message = extract_msg.Message(str(path))
    try:
        content = "\n".join(filter(None, [message.subject, message.body]))
        metadata = {
            "sender": message.sender or "",
            "to": message.to or "",
            "date": str(message.date or ""),
        }
        return document_from(path, content, metadata)
    finally:
        message.close()
