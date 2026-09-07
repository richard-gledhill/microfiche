"""Parses Outlook .msg email messages via extract-msg."""

from __future__ import annotations

from pathlib import Path

import extract_msg

from core.models.document import Document


def parse(path: Path) -> Document:
    message = extract_msg.Message(str(path))
    try:
        content = "\n".join(filter(None, [message.subject, message.body]))
        metadata = {
            "sender": message.sender or "",
            "to": message.to or "",
            "date": str(message.date or ""),
        }
        return Document(
            file_path=path,
            file_name=path.name,
            extension=path.suffix.lower(),
            content=content,
            metadata=metadata,
        )
    finally:
        message.close()
