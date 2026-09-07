"""Sortable unit model: a file or a whole folder to be filed atomically."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from core.models.document import Document


class SortableUnit(BaseModel):
    """A single item from the sorting inbox: either one file, or one folder kept whole.

    A folder unit is only produced when the caller opts in to ``--keep-folders`` - see
    ``core.scanner.scan_sorting_inbox``. It carries every supported document found inside the
    folder so the classifier can pick a dominant (group, category) for the folder as a whole.
    """

    source_path: Path
    kind: Literal["file", "folder"]
    documents: list[Document]
