"""Filesystem helpers: exclusion matching and safe (never-overwrite, never-delete) moves."""

from __future__ import annotations

import fnmatch
import shutil
from pathlib import Path


def is_excluded(path: Path, patterns: list[str]) -> bool:
    """Return True if any component of ``path`` matches one of the exclusion glob patterns.

    ``path`` must be relative to the library root: every component is tested, so an absolute
    path would be excluded by an unrelated folder above the library. Use ``Library.is_excluded``.
    """

    return any(fnmatch.fnmatch(part, pattern) for part in path.parts for pattern in patterns)


def ensure_dir(path: Path) -> Path:
    """Create ``path`` (and any missing parents) if it doesn't exist yet, and return it."""

    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_move(source: Path, destination: Path) -> Path:
    """Move ``source`` to ``destination``, never overwriting an existing file/folder.

    Per the PRD's "never delete user files" constraint, this only ever raises rather than
    silently clobbering something that's already at the destination.

    Raises:
        FileExistsError: if ``destination`` already exists.
    """

    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing path: {destination}")  # noqa: TRY003
    ensure_dir(destination.parent)
    shutil.move(str(source), str(destination))
    return destination
