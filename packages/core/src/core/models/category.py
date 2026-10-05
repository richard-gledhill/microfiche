"""Taxonomy model describing the library's existing group/category folder structure."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Taxonomy(BaseModel):
    """The library's discovered structure: group name -> list of existing category names.

    This is rebuilt by ``core.library.library.Library.taxonomy`` on every run rather than
    persisted - the library's own folders are the taxonomy, per
    docs/development/architecture.md.
    """

    groups: dict[str, list[str]] = Field(default_factory=dict)

    @property
    def group_names(self) -> list[str]:
        """The names of all groups."""

        return list(self.groups.keys())

    def categories_for(self, group: str) -> list[str]:
        """The existing category names of ``group``, empty if there is no such group."""

        return self.groups.get(group, [])
