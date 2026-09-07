"""Discovers the library's existing group/category folder taxonomy."""

from __future__ import annotations

from pathlib import Path

from core.models.category import Taxonomy
from core.utils.filesystem import is_excluded


def discover_taxonomy(library_root: Path, exclusions: list[str], depth: int = 2) -> Taxonomy:
    """Walk ``library_root`` to depth 2 and return the existing ``{group: [category, ...]}`` structure.

    Only directory names are read - file contents are never touched - so this is cheap even
    against a library with 10,000+ files. Anything matching ``exclusions`` (e.g. the sorting
    inbox, dotfolders) is skipped entirely, at both levels.
    """

    if depth != 2:
        raise NotImplementedError("Only the default depth of 2 (group/category) is implemented so far.")

    groups: dict[str, list[str]] = {}
    for group_dir in sorted(p for p in library_root.iterdir() if p.is_dir()):
        if is_excluded(group_dir, exclusions):
            continue
        categories = [
            category_dir.name
            for category_dir in sorted(group_dir.iterdir())
            if category_dir.is_dir() and not is_excluded(category_dir, exclusions)
        ]
        groups[group_dir.name] = categories
    return Taxonomy(groups=groups)
