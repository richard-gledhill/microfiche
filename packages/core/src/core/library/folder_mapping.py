"""Resolves the on-disk target path for a given (group, category) classification."""

from __future__ import annotations

from pathlib import Path


def resolve_target_path(library_root: Path, group: str, category: str) -> Path:
    """Return the folder a document/unit should be filed into for the given group and category."""

    return library_root / group / category
