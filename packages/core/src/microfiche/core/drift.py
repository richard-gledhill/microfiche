"""Noticing that a filed document was moved, edited or removed by hand since microfiche filed it.

The ledger records where every unit was filed. A person who reorganises the library in Obsidian or Explorer makes those
paths wrong, and ``rollback`` and ``reclassify`` then work from places that are no longer true. This module compares the
ledger with the filesystem, cheaply (one stat per recorded path), and, for a command that already holds the run lock,
records where moved units went so that the ledger is right again. It never moves, renames or deletes anything
(docs/development/adr/ADR-011-drift-check.md).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from microfiche.core.ledger import Ledger
from microfiche.core.library.library import Library
from microfiche.core.models.ledger import LedgerRecord
from microfiche.core.utils.hashing import file_hash, unit_hash

_logger = logging.getLogger(__name__)

# region Constants and types


class DriftState(StrEnum):
    """What became of a filed unit."""

    MOVED = "moved"
    MISSING = "missing"
    MODIFIED = "modified"


@dataclass(frozen=True)
class DriftItem:
    """One filed unit that is not as the ledger says.

    Attributes:
        path: Where the ledger has it, relative to the library with forward slashes.
        state: ``MOVED`` (found at ``new_path``), ``MISSING`` (gone, and not found by content) or ``MODIFIED`` (there, but
            its content differs from what was filed).
        new_path: Where a moved unit now is, relative to the library; ``None`` otherwise.
        record: The ledger record the unit was found out of place against.
    """

    path: str
    state: DriftState
    new_path: str | None = None
    record: LedgerRecord | None = field(default=None, compare=False, repr=False)


@dataclass
class DriftReport:
    """What a drift check found: only the units that are not in place.

    Attributes:
        items: Each moved, missing or modified unit.
        recorded: Whether the moved units were written to the ledger (the check was made by a command holding the lock).
    """

    items: list[DriftItem] = field(default_factory=list)
    recorded: bool = False

    def of(self, state: DriftState) -> list[DriftItem]:
        """The items in ``state``."""

        return [item for item in self.items if item.state is state]

    @property
    def summary(self) -> str | None:
        """One line saying what was found, or ``None`` if everything is in place."""

        parts = [
            f"{len(found)} {label}"
            for found, label in (
                (self.of(DriftState.MOVED), "moved"),
                (self.of(DriftState.MISSING), "missing"),
                (self.of(DriftState.MODIFIED), "edited"),
            )
            if found
        ]
        if not parts:
            return None
        count = len(self.items)
        recorded = "; recorded" if self.recorded and self.of(DriftState.MOVED) else ""
        return f"{count} filed item{'s' if count != 1 else ''}: {', '.join(parts)}{recorded}"


# endregion


# region Public API


def check_drift(library: Library) -> DriftReport:
    """Find the units the ledger has that are no longer where it says.

    A unit that is still there is not read. Only when one is missing is the library searched for it: among files not
    already accounted for by the ledger that have the same extension (or, for a folder filed whole, folders of the same
    name), by content hash, each read at most once. A unit is moved only if exactly one such place matches. One that was
    moved *and* edited, or moved and renamed as a folder, cannot be found and is missing.

    Args:
        library: The library to check.

    Returns:
        The moved and missing units. Edited ones are not looked for here (see ``find_modified``).
    """

    records = Ledger(library.state_dir).current()
    root = library.root
    gone = [record for record in records if not (root / record.path).exists()]
    if not gone:
        return DriftReport()

    accounted = {root / record.path for record in records}
    bundles = {root / record.path for record in records if record.unit_type == "folder"}
    files_by_suffix, folders_by_name = _candidates(library, accounted, bundles)
    claimed: set[Path] = set()
    hashes: dict[Path, str | None] = {}
    report = DriftReport()
    for record in gone:
        found = _find(record, files_by_suffix, folders_by_name, hashes, claimed)
        if found is None:
            _logger.debug("drift: %s is missing", record.path)
            report.items.append(DriftItem(record.path, DriftState.MISSING, record=record))
        else:
            claimed.add(found)
            _logger.debug("drift: %s moved to %s", record.path, library.relative(found))
            report.items.append(DriftItem(record.path, DriftState.MOVED, library.relative(found), record))
    return report


def record_moves(library: Library, report: DriftReport) -> None:
    """Write a ``relocated`` ledger record for each moved unit in ``report``, so the ledger points at its new place.

    The caller holds the run lock. Nothing on disk moves. Sets ``report.recorded``.

    Args:
        library: The library the report was made for.
        report: The result of ``check_drift``.
    """

    now = datetime.now()
    relocated = [
        item.record.model_copy(
            update={"event": "relocated", "path": item.new_path, "original_path": item.path, "timestamp": now}
        )
        for item in report.of(DriftState.MOVED)
        if item.record is not None and item.new_path is not None
    ]
    Ledger(library.state_dir).append(relocated)
    report.recorded = bool(relocated)


def find_modified(library: Library, paths: Iterable[Path]) -> list[DriftItem]:
    """Which of ``paths`` hold something other than what was filed there.

    Reads each path that the ledger has a record for, so call it only for files the command reads anyway.

    Args:
        library: The library the paths are in.
        paths: Filed files or folders (absolute).

    Returns:
        A ``MODIFIED`` item for each whose content hash differs from the ledger's.
    """

    by_path = {record.path: record for record in Ledger(library.state_dir).current()}
    modified: list[DriftItem] = []
    for path in paths:
        record = by_path.get(library.relative(path))
        if record is None or not path.exists():
            continue
        try:
            changed = unit_hash(path) != record.content_hash
        except OSError:
            continue
        if changed:
            modified.append(DriftItem(record.path, DriftState.MODIFIED, record=record))
    return modified


# endregion


# region Helpers


def _candidates(
    library: Library, accounted: set[Path], bundles: set[Path]
) -> tuple[dict[str, list[Path]], dict[str, list[Path]]]:
    """Files by extension and folders by name that the ledger does not account for, and so could be a moved unit."""

    files: dict[str, list[Path]] = defaultdict(list)
    folders: dict[str, set[Path]] = defaultdict(set)
    for entry in library.walk():
        path = Path(entry.path)
        if path in accounted or any(parent in bundles for parent in path.parents):
            continue
        files[path.suffix.casefold()].append(path)
        for parent in path.parents:
            if parent == library.root or library.root not in parent.parents:
                break
            if parent not in accounted:
                folders[parent.name.casefold()].add(parent)
    return files, {name: sorted(paths) for name, paths in folders.items()}


def _find(
    record: LedgerRecord,
    files_by_suffix: dict[str, list[Path]],
    folders_by_name: dict[str, list[Path]],
    hashes: dict[Path, str | None],
    claimed: set[Path],
) -> Path | None:
    """The one unclaimed place whose content is ``record``'s, or ``None`` if there is none or more than one."""

    recorded = Path(record.path)
    if record.unit_type == "folder":
        candidates = folders_by_name.get(recorded.name.casefold(), [])
        digest = unit_hash
    else:
        candidates = files_by_suffix.get(recorded.suffix.casefold(), [])
        digest = file_hash
    matches = [
        path for path in candidates if path not in claimed and _hash(path, digest, hashes) == record.content_hash
    ]
    return matches[0] if len(matches) == 1 else None


def _hash(path: Path, digest: Callable[[Path], str], hashes: dict[Path, str | None]) -> str | None:
    """``digest`` of ``path``, remembered; ``None`` if it cannot be read."""

    if path not in hashes:
        try:
            hashes[path] = digest(path)
        except OSError:
            hashes[path] = None
    return hashes[path]


# endregion
