"""Classification result models used by the rules engine and the AI fallback."""

from __future__ import annotations

from pydantic import BaseModel


class GroupMatch(BaseModel):
    """Result of resolving which library group (level 1, e.g. a project) a document belongs to."""

    name: str | None
    confidence: float
    reason: str


class CategoryMatch(BaseModel):
    """Result of resolving which category (level 2) within a group a document belongs to."""

    name: str | None
    confidence: float
    reason: str


class ClassificationResult(BaseModel):
    """Combined group + category classification for a single document or sortable unit.

    Attributes:
        group: The group decision.
        category: The category decision.
        overall_confidence: The weaker of the two stages' confidence.
        classified_by: Which resolver(s) decided - e.g. ``rules_engine``, ``ai_fallback`` or
            ``rules_engine+ai_fallback`` when each decided a different stage.
        confident: Whether the unit may be filed without review: both a group and a category
            were resolved and ``overall_confidence`` reached the classifier's threshold.
    """

    group: GroupMatch
    category: CategoryMatch
    overall_confidence: float
    classified_by: str
    confident: bool
