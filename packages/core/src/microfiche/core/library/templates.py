"""Creates a new group folder (e.g. a project) with its category subfolders from a named template.

Not yet wired to a CLI command (the current CLI surface assumes the library and its groups
already exist - see docs/development/architecture.md, section 8). No templates ship with microfiche
yet; a future `init` command would bring a catalog, using the same folder-tree shape as
``microfiche.core.library.library_file``.
"""

from __future__ import annotations

from pathlib import Path

from microfiche.core.utils.filesystem import ensure_dir


def create_library_group(library_root: Path, project_name: str, template_categories: list[str]) -> Path:
    """Create ``library_root/project_name`` with one subfolder per category in ``template_categories``.

    Args:
        library_root: The library's root folder.
        project_name: The name of the new group folder.
        template_categories: The category subfolders to create inside it.

    Returns:
        The path of the new group folder.
    """

    group_path = ensure_dir(library_root / project_name)
    for category in template_categories:
        ensure_dir(group_path / category)
    return group_path
