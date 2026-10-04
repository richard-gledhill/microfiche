"""Creates a new group folder (e.g. a project) with its category subfolders from a named template.

Not yet wired to a CLI command (the current CLI surface assumes the library and its groups
already exist - see docs/development/architecture.md, section 8) but kept here since
microfiche-config/library_templates.yaml already ships default templates for a future `create-library`/
`init` command.
"""

from __future__ import annotations

from pathlib import Path

from core.utils.filesystem import ensure_dir


def create_library_group(library_root: Path, project_name: str, template_categories: list[str]) -> Path:
    """Create ``library_root/project_name`` with one subfolder per category in ``template_categories``."""

    group_path = ensure_dir(library_root / project_name)
    for category in template_categories:
        ensure_dir(group_path / category)
    return group_path
