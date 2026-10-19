"""Keeping the library file in step with the library's folders.

The folders stay the authority on what exists (docs/development/architecture/overview.md, section 1). The sync compares
``Library.structure()`` with ``microfiche-library.json`` and appends an entry, with no hints, for each folder that
has none. It never changes or removes an entry the user wrote, and never creates or removes a folder: an entry
whose folder has gone is only reported.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from microfiche.core.library.library import Library
from microfiche.core.library.library_file import (
    LIBRARY_FILENAME,
    WILDCARD,
    FolderNode,
    LibraryFile,
    can_be_entry_name,
    load_library_file,
)

_logger = logging.getLogger(__name__)


# region Constants and types


@dataclass
class LibrarySync:
    """What one sync found, and whether it could write it down.

    Attributes:
        created: The library file did not exist and has been written.
        added: Folders that had no entry and were given one, as paths inside the library with forward slashes
            (``Project Phoenix``, ``Project Phoenix/01 Requirements``).
        missing: Entries whose folder is no longer there. They are kept in the file.
        possible_renames: A ``(missing, added)`` pair where exactly one entry went and exactly one folder
            appeared in the same place, so the folder may have been renamed. Nothing is carried over: the new
            entry starts with no hints.
        write_error: Why the file could not be written, or ``None``. ``added`` then lists what a write would
            have added, and the next run tries again.
    """

    created: bool = False
    added: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    possible_renames: list[tuple[str, str]] = field(default_factory=list)
    write_error: str | None = None


# endregion


# region Public API


def sync_library_file(library: Library) -> LibrarySync:
    """Add an entry to the library file for every folder that has none, and report entries with no folder.

    Matching is by folder name, ignoring case, among siblings. An entry named ``*`` stands for every folder at its
    level that has no entry of its own, so where one exists nothing is added for those folders; it is left alone
    and is never reported missing. A folder whose name cannot be an entry (it has a path separator or edge
    whitespace, or differs from a sibling only by case) is skipped with a warning, so the file stays loadable.

    The file is read afresh, so a change made since the library was opened is kept. It is written only when
    something was added, as a temporary file renamed into place so a reader never sees half of it. Entries the
    user wrote keep their content and their order, and new ones are appended in sorted order; but the file is
    rewritten in the standard layout (two-space indent, keys in a fixed order, empty lists left out), so its
    formatting is not preserved.

    Args:
        library: The library to sync. Its library file is replaced with the merged one after a write.

    Returns:
        What was added and what is missing.

    Raises:
        ConfigError: If the existing library file is invalid. It is not overwritten.
    """

    path = library.state_dir / LIBRARY_FILENAME
    existed = path.is_file()
    existing = load_library_file(library.state_dir, library.config.library_structure.depth)
    library.library_file = existing
    sync = LibrarySync()
    groups = _merge(library, existing.groups, library.structure(), Path(), sync)
    _find_possible_renames(sync)
    for gone in sync.missing:
        _logger.warning("library file: %s has an entry but no folder", gone)
    if not sync.added:
        return sync

    merged = existing.model_copy(update={"groups": groups})
    try:
        _write(path, merged)
    except OSError as err:
        sync.write_error = str(err)
        _logger.warning("library file: could not write %s: %s", LIBRARY_FILENAME, err)
        return sync
    sync.created = not existed
    library.library_file = merged
    _logger.info("library file: added %d folder(s): %s", len(sync.added), ", ".join(sync.added))
    return sync


# endregion


# region Helpers


def _merge(
    library: Library, entries: list[FolderNode], folders: list[FolderNode], parent: Path, sync: LibrarySync
) -> list[FolderNode]:
    """``entries`` with a new one appended for each of ``folders`` that has none, recording what it finds in ``sync``."""

    by_name = {entry.name.casefold(): entry for entry in entries if entry.name != WILDCARD}
    has_wildcard = any(entry.name == WILDCARD for entry in entries)
    merged = list(entries)
    seen: set[str] = set()
    for folder in folders:
        if not can_be_entry_name(folder.name) or folder.name.casefold() in seen:
            _logger.warning("library file: not listing the folder %r: its name can't be an entry", parent / folder.name)
            continue
        seen.add(folder.name.casefold())
        entry = by_name.pop(folder.name.casefold(), None)
        if entry is None:
            if has_wildcard:  # a '*' entry already stands for this folder
                continue
            path = parent / folder.name
            sync.added.append(path.as_posix())
            children = _merge(library, [], folder.children, path, sync)
            merged.append(FolderNode(name=folder.name, children=children))
            continue
        children = _merge(library, entry.children, folder.children, parent / entry.name, sync)
        merged[merged.index(entry)] = entry.model_copy(update={"children": children})
    for entry in by_name.values():  # what is left named a folder that wasn't found
        path = parent / entry.name
        if not (library.root / path).exists():  # an excluded folder is still there, so it isn't missing
            sync.missing.append(path.as_posix())
    return merged


def _find_possible_renames(sync: LibrarySync) -> None:
    """Pair an entry that went with a folder that came, where each is the only one in its parent folder."""

    for gone in sync.missing:
        parent = Path(gone).parent
        siblings_gone = [path for path in sync.missing if Path(path).parent == parent]
        siblings_new = [path for path in sync.added if Path(path).parent == parent]
        if len(siblings_gone) == 1 and len(siblings_new) == 1:
            sync.possible_renames.append((gone, siblings_new[0]))


def _write(path: Path, library_file: LibraryFile) -> None:
    """Write ``library_file`` to ``path`` through a temporary file in the same folder, renamed into place."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    text = library_file.model_dump_json(indent=2, by_alias=True, exclude_defaults=True)
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text + "\n")
            handle.flush()
            os.fsync(handle.fileno())  # on disk before the rename, so a power cut can't leave an empty file
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


# endregion
