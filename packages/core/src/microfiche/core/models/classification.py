"""Classification result models used by the rules engine and the AI fallback."""

from __future__ import annotations

from pydantic import BaseModel


class GroupMatch(BaseModel):
    """Result of resolving which library group (level 1, e.g. a project) a document belongs to.

    ``candidates`` names the groups the evidence was too close to choose between, when ``name`` is ``None`` for that
    reason; it is empty otherwise.
    """

    name: str | None
    confidence: float
    reason: str
    candidates: tuple[str, ...] = ()


class CategoryMatch(BaseModel):
    """Result of resolving which category (level 2) within a group a document belongs to.

    ``candidates`` names the categories the evidence was too close to choose between, when ``name`` is ``None`` for
    that reason; it is empty otherwise.
    """

    name: str | None
    confidence: float
    reason: str
    candidates: tuple[str, ...] = ()


class ClassificationResult(BaseModel):
    """Combined group + category classification for a single document or sortable unit.

    Attributes:
        group: The group decision.
        category: The category decision, or ``None`` in a flat library (``depth`` 1), which has no categories.
            That is different from a ``CategoryMatch`` whose ``name`` is ``None``, which is a category that
            could not be resolved.
        overall_confidence: The weaker of the two stages' confidence (the group's, in a flat library).
        classified_by: Which resolver(s) decided - e.g. ``rules_engine``, ``ai_fallback`` or
            ``rules_engine+ai_fallback`` when each decided a different stage.
        confident: Whether the unit may be filed without review: every level the library has was resolved
            and ``overall_confidence`` reached the classifier's threshold.
    """

    group: GroupMatch
    category: CategoryMatch | None
    overall_confidence: float
    classified_by: str
    confident: bool

    @property
    def ambiguous(self) -> bool:
        """Whether a stage was held because the evidence was too close to choose between folders."""

        return bool(self.group.candidates or (self.category and self.category.candidates))

    @property
    def folders(self) -> tuple[str, ...] | None:
        """The folder names the unit belongs under, down from the library root, or ``None`` if unresolved.

        ``(group,)`` in a flat library, ``(group, category)`` otherwise. Filing code takes this, so it does not
        need to know how many levels the library has.
        """

        if self.group.name is None:
            return None
        if self.category is None:
            return (self.group.name,)
        if self.category.name is None:
            return None
        return (self.group.name, self.category.name)

    @property
    def reason(self) -> str:
        """Why the unit is where it is: the deepest level's reason, which says if an earlier level failed."""

        return (self.category or self.group).reason

    def held(self, why: str) -> ClassificationResult:
        """The same classification, no longer confident, with ``why`` added to the reason.

        The group and category stay as classified, so ``review`` can show where the unit would have gone.
        """

        if self.category is None:
            return self.model_copy(
                update={
                    "confident": False,
                    "group": self.group.model_copy(update={"reason": f"{self.group.reason}; but {why}"}),
                }
            )
        return self.model_copy(
            update={
                "confident": False,
                "category": self.category.model_copy(update={"reason": f"{self.category.reason}; but {why}"}),
            }
        )
