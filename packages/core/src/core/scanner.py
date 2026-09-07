"""Scans the library's sorting/ inbox and builds the list of SortableUnits to process.

Per the ADR, `sorting/` is a single, library-wide inbox at the library root - not one per
project/group.
"""

from __future__ import annotations

from pathlib import Path

from core.extractor import extract
from core.models.unit import SortableUnit
from core.parsers import SUPPORTED_EXTENSIONS

SORTING_FOLDER_NAME = "sorting"


def scan_sorting_inbox(library_root: Path, *, keep_folders: bool = False) -> list[SortableUnit]:
    """Scan ``library_root/sorting`` and return the units ready for classification.

    Loose supported files become single-document units. Sub-folders are only descended into
    (and kept whole as one unit) when ``keep_folders`` is True; otherwise they're left alone
    for the user to handle manually.
    """

    inbox = library_root / SORTING_FOLDER_NAME
    if not inbox.exists():
        return []

    units: list[SortableUnit] = []
    for entry in sorted(inbox.iterdir()):
        if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
            units.append(SortableUnit(source_path=entry, kind="file", documents=[extract(entry)]))
        elif entry.is_dir() and keep_folders:
            documents = [
                extract(file_path)
                for file_path in sorted(entry.rglob("*"))
                if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS
            ]
            if documents:
                units.append(SortableUnit(source_path=entry, kind="folder", documents=documents))

    return units
