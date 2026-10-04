"""Sortable unit model: a file or a whole folder to be filed atomically."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from core.models.document import Document, UnreadableDocument

# Todo: Review if it makes sense to keep SortableUnit in a separate file from document.py.


class SortableUnit(BaseModel):
    """
    Represents a unit of data that can be sorted, such as a file or folder.

    A single item from the sorting inbox: either one file, or one folder kept whole.

    This class is designed to encapsulate information about a sortable entity,
    including its source path, type (e.g., file or folder), and any associated
    documents. It is primarily intended to organize and manage entities in a
    structured manner.

    A folder unit is only produced when the caller opts in to ``--keep-folders`` - see
    ``core.scanner.scan_sorting_inbox``. It carries every supported document found inside the
    folder so the classifier can pick a dominant (group, category) for the folder as a whole.

    Attributes:
        source_path (Path): The file system path to the source of the unit.
        kind (Literal["file", "folder"]): The category of the unit, indicating
            whether it is a file or a folder.
        documents (list[Document]): A collection of document objects associated
            with this unit.
        unreadable (list[UnreadableDocument]): Supported files in the unit that could not be
            read. They don't take part in classification; a unit with no readable document at
            all is left for review, with these as the reason.
    Todo
        - Is there a skeleton class for a folder unit, or can this be extended from SortableUnit?
    """

    source_path: Path
    kind: Literal["file", "folder"]
    documents: list[Document]
    unreadable: list[UnreadableDocument] = Field(default_factory=list)
