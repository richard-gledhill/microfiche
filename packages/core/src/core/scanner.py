"""Scans the library's inbox and builds the list of SortableUnits to process.

Per the ADR, the inbox is a single, library-wide folder at the library root - not one per group.
"""

from __future__ import annotations

from core.library.library import Library
from core.models.unit import SortableUnit
from core.parsers import is_supported, read_documents


def scan_sorting_inbox(library: Library, *, keep_folders: bool | None = None) -> list[SortableUnit]:
    """Scan the library's inbox and return the units ready for classification.

    The inbox is ``library.inbox`` (``_sorting`` unless the config's
    ``[library_structure] library_inbox`` says otherwise).

    Files that can't be read (corrupt, say) don't stop the scan: they are recorded on their unit's
    ``unreadable`` list, so the unit is left for review rather than the whole run failing.

    Loose supported files become single-document units. A sub-folder with at least one supported file
    is descended into either way:

    - keeping folders whole (the default): the folder is one unit, filed under its dominant category;
    - not keeping them: every supported file in it, including those in nested sub-folders, is a
      single-document unit of its own, with ``origin_folder`` set to the folder so that it can be removed
      once it is empty.

    A folder with no supported file is left alone for the user to handle manually.

    Args:
        library: The library whose inbox to scan.
        keep_folders: Whether to keep each folder with supported files whole as one unit. ``None``
            (the default) uses the library's ``[sorting] keep_folders`` setting.

    Returns:
        The ``SortableUnit`` objects for the files and, optionally, folders in the inbox.
        Empty if the inbox doesn't exist.

    Todo:
        - Raise warning for handle empty sorting inbox directory.
    """

    inbox = library.inbox
    if not inbox.exists():
        return []
    if keep_folders is None:
        keep_folders = library.config.sorting.keep_folders

    units: list[SortableUnit] = []
    for entry in sorted(inbox.iterdir()):
        if entry.is_file() and is_supported(entry):
            read = read_documents([entry])
            units.append(
                SortableUnit(source_path=entry, kind="file", documents=read.documents, unreadable=read.unreadable)
            )
        elif entry.is_dir():
            inside = [path for path in sorted(entry.rglob("*")) if path.is_file()]
            if keep_folders:
                read = read_documents(inside)
                if read.documents or read.unreadable:
                    units.append(
                        SortableUnit(
                            source_path=entry, kind="folder", documents=read.documents, unreadable=read.unreadable
                        )
                    )
            else:
                for path in inside:
                    if is_supported(path):
                        read = read_documents([path])
                        units.append(
                            SortableUnit(
                                source_path=path,
                                kind="file",
                                documents=read.documents,
                                unreadable=read.unreadable,
                                origin_folder=entry,
                            )
                        )

    return units
