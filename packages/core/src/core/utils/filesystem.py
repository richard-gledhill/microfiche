"""Filesystem helpers: name matching, link detection and safe (never-overwrite, never-delete) moves."""

from __future__ import annotations

import fnmatch
import stat
from pathlib import Path

# Windows reparse tags that make a path a link: a symlink, or a junction (a "mount point").
_LINK_REPARSE_TAGS = frozenset({stat.IO_REPARSE_TAG_SYMLINK, stat.IO_REPARSE_TAG_MOUNT_POINT})


def is_excluded(path: Path, patterns: list[str]) -> bool:
    """Return True if any component of ``path`` matches one of the exclusion glob patterns.

    ``path`` must be relative to the library root: every component is tested, so an absolute
    path would be excluded by an unrelated folder above the library. Use ``Library.is_excluded``.

    Args:
        path: A path relative to the library root.
        patterns: Glob patterns to test each component against.

    Returns:
        ``True`` if any component matches a pattern.
    """

    return any(name_matches(part, patterns) for part in path.parts)


def name_matches(name: str, patterns: list[str]) -> bool:
    """Return True if ``name`` (a single file or folder name) matches any of the glob ``patterns``.

    Args:
        name: A file or folder name, not a path.
        patterns: Glob patterns to test it against.

    Returns:
        ``True`` if any pattern matches. Case is ignored where the filesystem ignores it (Windows).
    """

    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def is_link(path: Path) -> bool:
    """Return True if ``path`` is a symbolic link or, on Windows, a junction.

    A junction is a folder that is really another folder elsewhere. Following either one could
    wander out of the library or around in a loop, so the scans skip them.

    Other Windows reparse points are *not* links: OneDrive's on-demand placeholder files carry the
    reparse-point attribute too, so the reparse *tag* is checked and only a mount point counts.

    Args:
        path: The file or folder to test. It is not followed.

    Returns:
        ``True`` for a symlink or a junction, ``False`` for anything else, including a missing path.
    """

    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0) in _LINK_REPARSE_TAGS


def ensure_dir(path: Path) -> Path:
    """Create ``path`` (and any missing parents) if it doesn't exist yet.

    Args:
        path: The folder to ensure exists.

    Returns:
        ``path``.
    """

    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_move(source: Path, destination: Path) -> Path:
    """Move ``source`` to ``destination`` by renaming it. Never overwrites, never copies, never deletes.

    A rename is one step that either happens or does not, so a move that fails leaves everything as it
    was. ``shutil.move`` is avoided on purpose: when a rename fails it quietly copies the file and then
    tries to delete the original, which leaves a stray copy behind if the delete fails too. That is
    exactly what happens on Windows when another program, such as Word, has the file open.

    Args:
        source: The file or folder to move.
        destination: Where to move it.

    Returns:
        ``destination``.

    Raises:
        FileExistsError: if ``destination`` already exists.
        OSError: if the rename fails - on Windows a ``PermissionError`` when another program has the
            file open, or an error when ``destination`` is on a different volume. Nothing has moved.
    """

    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing path: {destination}")  # noqa: TRY003
    ensure_dir(destination.parent)
    source.rename(destination)
    return destination
