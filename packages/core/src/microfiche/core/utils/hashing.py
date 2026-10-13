"""File hashing, used for duplicate detection and change tracking."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 65536


def file_hash(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's contents.

    Args:
        path: The file to hash.

    Returns:
        The hex digest.
    """

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unit_hash(path: Path) -> str:
    """Return a content hash for a sortable unit: a file's own hash, or a folder's manifest hash.

    A folder's hash is the SHA-256 of one ``<relative posix path>:<file hash>`` line per file
    inside it (every file, supported or not, since the whole folder moves), in sorted path
    order - so it changes if any file is added, removed, renamed, or edited, and is the same on
    every OS.

    Args:
        path: The file or folder to hash.

    Returns:
        The hex digest.
    """

    if path.is_file():
        return file_hash(path)

    files = sorted(
        ((child.relative_to(path).as_posix(), child) for child in path.rglob("*") if child.is_file()),
        key=lambda entry: entry[0],
    )
    digest = hashlib.sha256()
    for relative_path, child in files:
        digest.update(f"{relative_path}:{file_hash(child)}\n".encode())
    return digest.hexdigest()
