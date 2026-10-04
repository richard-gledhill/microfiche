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
    """Combined group + category classification for a single document or sortable unit."""

    group: GroupMatch
    category: CategoryMatch
    overall_confidence: float
    classified_by: str
