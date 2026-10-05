"""Validation helpers for library paths and inputs."""

from __future__ import annotations

from pathlib import Path


def validate_library_root(path: Path) -> None:
    """Raise if ``path`` isn't an existing directory.

    Args:
        path: The path to check.

    Raises:
        NotADirectoryError: if ``path`` doesn't exist or isn't a directory.
    """

    if not path.exists():
        raise NotADirectoryError(f"Library root does not exist: {path}")  # noqa: TRY003
    if not path.is_dir():
        raise NotADirectoryError(f"Library root is not a directory: {path}")  # noqa: TRY003
