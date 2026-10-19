"""Taxonomy model describing the library's existing group/category folder structure."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Taxonomy(BaseModel):
    """The library's discovered structure: group name -> list of existing category names.

    This is rebuilt by ``microfiche.core.library.library.Library.taxonomy`` on every run rather than
    persisted - the library's own folders are the taxonomy, per
    docs/development/architecture/overview.md.

    Attributes:
        groups: Each group and its category names. In a flat library (``depth`` 1) the lists are empty
            because there are no categories, not because a group has none yet.
        depth: How many levels of folders the library has (``[library_structure] depth``): 1 is groups only,
            2 is group then category. It is what tells an empty category list at depth 1 (nothing to choose,
            the group is the destination) from one at depth 2 (a group with nowhere to file into).
    """

    groups: dict[str, list[str]] = Field(default_factory=dict)
    depth: int = 2

    @property
    def is_flat(self) -> bool:
        """Whether the library has groups only, so documents are filed straight into a group folder."""

        return self.depth == 1

    @property
    def group_names(self) -> list[str]:
        """The names of all groups."""

        return list(self.groups.keys())

    def categories_for(self, group: str) -> list[str]:
        """The existing category names of ``group``, empty if there is no such group."""

        return self.groups.get(group, [])
