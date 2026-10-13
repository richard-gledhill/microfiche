"""Sortable unit model: a file or a whole folder to be filed atomically."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from microfiche.core.models.document import Document, UnreadableDocument
from pydantic import BaseModel, Field

# Todo: Review if it makes sense to keep SortableUnit in a separate file from document.py.


class SortableUnit(BaseModel):
    """A single item from the sorting inbox: either one file, or one folder kept whole.

    A folder unit is only produced when folders are kept whole (``[sorting] keep_folders``) - see
    ``microfiche.core.scanner.scan_sorting_inbox``. It carries every supported document found inside the
    folder so the classifier can pick a dominant (group, category) for the folder as a whole.
    When folders are not kept whole, each supported file inside one becomes a file unit of its own.

    Attributes:
        source_path: The file system path to the source of the unit.
        kind: Whether the unit is a ``"file"`` or a ``"folder"``.
        documents: The readable documents in the unit.
        unreadable: Supported files in the unit that could not be read. They don't take part in
            classification; a unit with no readable document at all is left for review, with
            these as the reason.
        origin_folder: For a file unit taken out of an inbox folder, that top-level inbox folder (the file may be
            in a sub-folder of it). ``None`` for a file loose in the inbox and for a folder unit. Once the folder's
            files are filed, ``microfiche.core.filer.file_batch`` removes it if nothing else is left in it.

    Todo:
        - Is there a skeleton class for a folder unit, or can this be extended from SortableUnit?
    """

    source_path: Path
    kind: Literal["file", "folder"]
    documents: list[Document]
    unreadable: list[UnreadableDocument] = Field(default_factory=list)
    origin_folder: Path | None = None
