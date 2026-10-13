"""Scans the library's inbox and builds the list of SortableUnits to process.

Per the ADR, the inbox is a single, library-wide folder at the library root - not one per group.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from microfiche.core.library.library import Library
from microfiche.core.models.unit import SortableUnit
from microfiche.core.parsers import is_supported, read_documents
from microfiche.core.utils.filesystem import is_link, name_matches

_logger = logging.getLogger(__name__)


@dataclass
class InboxScan:
    """What a scan of the inbox found.

    Attributes:
        units: The units ready for classification.
        skipped_links: Symbolic links and junctions that were passed over. They are never followed,
            read or filed, so the user is told about them.
    """

    units: list[SortableUnit] = field(default_factory=list)
    skipped_links: list[Path] = field(default_factory=list)


def scan_sorting_inbox(library: Library, *, keep_folders: bool | None = None) -> InboxScan:
    """Scan the library's inbox and return the units ready for classification.

    The inbox is ``library.inbox`` (``_sorting`` unless the config's
    ``[library_structure] library_inbox`` says otherwise).

    Anything whose name matches the config's ``[sorting] ignore`` patterns is skipped without
    comment, and a symbolic link or junction is skipped and listed in ``skipped_links``; neither
    is followed, read or filed.

    Files that can't be read (corrupt, say) don't stop the scan: they are recorded on their unit's
    ``unreadable`` list, so the unit is left for review rather than the whole run failing. A file
    bigger than ``[parsing] max_file_mb`` is treated the same way, without being opened.

    Loose supported files become single-document units. A sub-folder with at least one supported file
    is descended into either way:

    - keeping folders whole (the default): the folder is one unit, filed under its dominant group or category;
    - not keeping them: every supported file in it, including those in nested sub-folders, is a
      single-document unit of its own, with ``origin_folder`` set to the folder so that it can be removed
      once it is empty.

    A folder with no supported file is left alone for the user to handle manually.

    Args:
        library: The library whose inbox to scan.
        keep_folders: Whether to keep each folder with supported files whole as one unit. ``None``
            (the default) uses the library's ``[sorting] keep_folders`` setting.

    Returns:
        The units, and the links that were skipped. Both are empty if the inbox doesn't exist.

    Todo:
        - Raise warning for handle empty sorting inbox directory.
    """

    scan = InboxScan()
    inbox = library.inbox
    if not inbox.exists():
        _logger.info("inbox %s does not exist; nothing to scan", inbox.name)
        return scan
    config = library.config
    if keep_folders is None:
        keep_folders = config.sorting.keep_folders
    ignore, max_bytes = config.sorting.ignore, config.parsing.max_file_bytes

    for entry in sorted(inbox.iterdir()):
        if name_matches(entry.name, ignore):
            _logger.debug("ignored %s: it matches [sorting] ignore", entry.name)
            continue
        if is_link(entry):
            _skip_link(entry, scan.skipped_links)
        elif entry.is_file():
            if is_supported(entry):
                scan.units.append(_file_unit(entry, max_bytes))
        elif entry.is_dir():
            inside = _files_under(entry, ignore, scan.skipped_links)
            scan.units.extend(_folder_units(entry, inside, keep_folders, max_bytes))

    _logger.info(
        "scanned %s: %d unit(s) to classify, %d link(s) skipped", inbox.name, len(scan.units), len(scan.skipped_links)
    )
    return scan


def _file_unit(path: Path, max_bytes: int, origin_folder: Path | None = None) -> SortableUnit:
    """The single-document unit for one supported file, which is unreadable if it cannot be read or is too big."""

    read = read_documents([path], max_bytes=max_bytes)
    return SortableUnit(
        source_path=path, kind="file", documents=read.documents, unreadable=read.unreadable, origin_folder=origin_folder
    )


def _folder_units(folder: Path, files: list[Path], keep_folders: bool, max_bytes: int) -> list[SortableUnit]:
    """The units for an inbox folder holding ``files``: the folder as one unit, or one unit per supported file.

    Nothing at all if the folder holds no supported file.
    """

    if keep_folders:
        read = read_documents(files, max_bytes=max_bytes)
        if not (read.documents or read.unreadable):
            return []
        return [SortableUnit(source_path=folder, kind="folder", documents=read.documents, unreadable=read.unreadable)]
    return [_file_unit(path, max_bytes, origin_folder=folder) for path in files if is_supported(path)]


def _files_under(folder: Path, ignore: list[str], skipped_links: list[Path]) -> list[Path]:
    """Every file below ``folder``, sorted, leaving out ignored names and anything behind a link.

    Ignored names are dropped silently, and an ignored folder is not entered. A link is appended to
    ``skipped_links`` and not followed, whether it points at a file or a folder.
    """

    files: list[Path] = []
    for current, folders, names in os.walk(folder):
        here = Path(current)
        kept_folders: list[str] = []
        for name in sorted(folders):
            if name_matches(name, ignore):
                _logger.debug("ignored %s: it matches [sorting] ignore", name)
                continue
            if is_link(here / name):
                _skip_link(here / name, skipped_links)
            else:
                kept_folders.append(name)
        folders[:] = kept_folders  # os.walk only descends into what is left in this list
        for name in names:
            if name_matches(name, ignore):
                _logger.debug("ignored %s: it matches [sorting] ignore", name)
                continue
            if is_link(here / name):
                _skip_link(here / name, skipped_links)
            else:
                files.append(here / name)
    return sorted(files)


def _skip_link(link: Path, skipped_links: list[Path]) -> None:
    """Note a symbolic link or junction as skipped, and say why."""

    skipped_links.append(link)
    _logger.info("skipped link %s: links are never followed", link.name)
