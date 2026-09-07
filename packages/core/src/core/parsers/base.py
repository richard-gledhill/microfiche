"""Common parser interface: every format parser turns a file path into a Document."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from core.models.document import Document


class Parser(Protocol):
    def __call__(self, path: Path) -> Document: ...
