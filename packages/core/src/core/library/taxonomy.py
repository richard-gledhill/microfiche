"""Discovers the library's existing group/category folder taxonomy."""

from __future__ import annotations

from pathlib import Path

from core.models.category import Taxonomy
from core.utils.filesystem import is_excluded


def discover_taxonomy(library_root: Path, exclusions: list[str], depth: int = 2) -> Taxonomy:
    """Discover and build a taxonomy structure from a library directory.
    Walk ``library_root`` to depth 2 and return the existing ``{group: [category, ...]}`` structure.
    Only directory names are read - file contents are never touched - so this is cheap even
    against a library with 10,000+ files. Anything matching ``exclusions`` (e.g. the sorting
    inbox, dotfolders) is skipped entirely, at both levels.

    This function walks through the provided library directory and organizes it into
    a taxonomy structure consisting of groups and categories. Only directories that
    meet the inclusion criteria are included, and the function operates at a fixed
    depth of 2 (group/category). Any directory name matching the exclusions list is
    ignored. If a different depth is provided, the function raises a
    `NotImplementedError`.

    Args:
        library_root (Path): The root directory of the library from which to discover
            groups and categories.
        exclusions (list[str]): A list of directory names to exclude from the taxonomy
            discovery process.
        depth (int): The depth of exploration for taxonomy structure. Currently,
            only a depth of 2 is supported. Defaults to 2.

    Returns:
        Taxonomy: A `Taxonomy` object containing the discovered groups and categories
            organized into a dictionary-like structure.

    Raises:
        NotImplementedError: If a depth other than 2 is provided.
    Todo:
        - Add support for other depths in the future.
        - Improve error handling for invalid input types.
        - Validate depth input.
        - Consider merging from core.models.category import Taxonomy to improve code organization and module depth.
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
