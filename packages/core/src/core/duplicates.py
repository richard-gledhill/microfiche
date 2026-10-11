"""Spots inbox files that are exact copies of a file already in the library.

``sort`` checks each new file in the inbox against the library by content, so that dropping a file
that is already filed (or two copies of the same file at once) does not quietly create a second one.
Only new files are checked: a project often holds the same document in more than one place, so
duplicates already inside the library are never looked for or reported.

The library is not hashed up front. ``DuplicateIndex`` walks it once, on first use, reading only
file sizes, and hashes a file only when it has the same size as a file being checked.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from core.filer import destination_for
from core.library.library import Library
from core.models.classification import ClassificationResult
from core.models.unit import SortableUnit
from core.utils.hashing import file_hash

# region Constants and types


@dataclass(frozen=True)
class ExistingCopy:
    """A file with the same content as one being checked.

    Attributes:
        path: Where the copy is in the library, or, for a copy about to be filed, where it will go.
        pending_from: ``None`` for a file already in the library; otherwise the inbox file that is being
            filed to ``path`` in this run.
    """

    path: Path
    pending_from: Path | None = None


@dataclass
class Duplicate:
    """An inbox file left where it is because the library already has a copy of it.

    Attributes:
        unit: The inbox file.
        classification: What the classifier made of it; the file is classified like any other.
        existing: Where the copy is (see ``ExistingCopy.path``).
        reason: Why it was held, naming the copy and, if the file would be filed somewhere else, where.
    """

    unit: SortableUnit
    classification: ClassificationResult
    existing: Path
    reason: str


# endregion


# region Public API


class DuplicateIndex:
    """Finds library files whose content matches an inbox file, cheaply.

    Nothing is read until the first file is checked. Then the library is walked once - skipping the
    inbox, the state folder and excluded folders - recording each file's size. A file is hashed only
    if another file of the same size is in play, and each file is hashed at most once. Empty files
    are never duplicates of anything.

    A file that is about to be filed can be registered with ``add``, so a later inbox file with the
    same content is caught as a copy of it.

    Args:
        library: The library to look in.
    """

    def __init__(self, library: Library) -> None:
        self._library = library
        self._library_files: dict[int, list[Path]] | None = None
        self._pending: dict[int, list[tuple[Path, Path]]] = defaultdict(list)
        self._hashes: dict[Path, str | None] = {}

    def find(self, path: Path) -> list[ExistingCopy]:
        """Find every file in the library, or about to be filed, with the same content as ``path``.

        A file that cannot be read (locked, or removed since the walk) is treated as not matching.

        Args:
            path: The inbox file to look for.

        Returns:
            The copies: those already in the library first, in path order, then those about to be filed.
        """

        size = _size(path)
        if not size:
            return []
        if self._library_files is None:
            self._library_files = self._walk_library()
        in_library = self._library_files.get(size, [])
        pending = self._pending.get(size, [])
        if not in_library and not pending:
            return []

        wanted = self._hash(path)
        if wanted is None:
            return []
        copies = [ExistingCopy(candidate) for candidate in in_library if self._hash(candidate) == wanted]
        copies += [ExistingCopy(destination, source) for source, destination in pending if self._hash(source) == wanted]
        return copies

    def add(self, source: Path, destination: Path) -> None:
        """Register an inbox file that is going to be filed, so a later identical file is held as its copy.

        Args:
            source: The inbox file, which stays where it is until the batch is filed.
            destination: Where it will be filed.
        """

        size = _size(source)
        if size:
            self._pending[size].append((source, destination))

    def check(self, unit: SortableUnit, classification: ClassificationResult) -> Duplicate | None:
        """Say whether ``unit`` is a copy of something already in the library or about to be filed.

        Only a file unit is checked. A folder unit is never held as a duplicate.

        Args:
            unit: The inbox unit.
            classification: Its classification, used to word the reason and to prefer the copy that
                is where the unit would be filed.

        Returns:
            The duplicate, or ``None`` if the unit has no copy.
        """

        if unit.kind != "file":
            return None
        copies = self.find(unit.source_path)
        if not copies:
            return None

        placement = _Placement(self._library, unit, classification)
        best = min(copies, key=placement.rank)
        return Duplicate(unit, classification, best.path, placement.reason(best))

    def _walk_library(self) -> dict[int, list[Path]]:
        """Group every non-excluded file in the library by size, reading directory entries only."""

        by_size: dict[int, list[Path]] = defaultdict(list)
        folders = [self._library.root]
        while folders:
            try:
                with os.scandir(folders.pop()) as scan:
                    entries = sorted(scan, key=lambda entry: entry.name)
            except OSError:
                continue
            for entry in entries:
                path = Path(entry.path)
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if not self._library.is_excluded(path):
                            folders.append(path)
                    elif entry.is_file(follow_symlinks=False) and not self._library.is_excluded(path):
                        size = entry.stat().st_size
                        if size:
                            by_size[size].append(path)
                except OSError:
                    continue
        for paths in by_size.values():
            paths.sort()
        return by_size

    def _hash(self, path: Path) -> str | None:
        """The content hash of ``path``, remembered; ``None`` if it cannot be read."""

        if path not in self._hashes:
            try:
                self._hashes[path] = file_hash(path)
            except OSError:
                self._hashes[path] = None
        return self._hashes[path]


# endregion


# region Helpers


class _Placement:
    """Compares where a unit would be filed with where a copy of it is, to rank copies and word the reason."""

    def __init__(self, library: Library, unit: SortableUnit, classification: ClassificationResult) -> None:
        self._library = library
        self._classification = classification
        self._group = classification.group.name
        self._category = classification.category.name
        self._destination = (
            destination_for(library, self._group, self._category, unit.source_path.name)
            if self._group is not None and self._category is not None
            else None
        )

    def rank(self, copy: ExistingCopy) -> int:
        """Order copies: at the destination, in the destination folder, elsewhere, then not yet filed."""

        if copy.pending_from is not None:
            return 3
        if self._destination is None:
            return 2
        if copy.path == self._destination:
            return 0
        return 1 if self._in_destination_folder(copy.path) else 2

    def reason(self, copy: ExistingCopy) -> str:
        """Why the unit is held: names the copy and, when the classifier would file it elsewhere, where."""

        found = self._library.relative(copy.path)
        if copy.pending_from is not None:
            return (
                f"identical to '{copy.pending_from.name}', which is being filed this run to "
                f"{self._library.relative(copy.path.parent)}"
            )
        if self._group is None or self._category is None:
            return f"identical to {found}; could not be classified"

        target = f"{self._group}/{self._category}"
        if not self._classification.confident:
            return f"identical to {found}; the classifier suggests {target} but is not confident"
        if copy.path == self._destination:
            return f"identical to {found}, already filed where this would go"
        if self._in_destination_folder(copy.path):
            return f"identical to {found}, in the folder this would be filed to"
        return f"identical to {found}; this would be filed in {target}"

    def _in_destination_folder(self, path: Path) -> bool:
        if self._group is None or self._category is None:
            return False
        return self._library.filed_under(path, self._group, self._category)


def _size(path: Path) -> int | None:
    """The size of ``path`` in bytes, or ``None`` if it cannot be read."""

    try:
        return path.stat().st_size
    except OSError:
        return None


# endregion
