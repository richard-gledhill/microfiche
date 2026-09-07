"""File hashing, used for duplicate detection and change tracking."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 65536


def file_hash(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's contents."""

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
