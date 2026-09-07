"""Document model representing a single extracted source file."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class Document(BaseModel):
    """A single document that has been extracted and is ready for classification."""

    file_path: Path
    file_name: str
    extension: str
    content: str
    metadata: dict[str, str] = Field(default_factory=dict)
