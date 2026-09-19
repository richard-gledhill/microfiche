"""Stage 1 classification: which library group (project) does a document belong to."""

from __future__ import annotations

from thefuzz import fuzz

from core.models.classification import GroupMatch

_FUZZY_MATCH_THRESHOLD = 85


def match_group(text: str, group_names: list[str]) -> GroupMatch:
    """Match ``text`` against known group names by substring, then fuzzy match.

    Returns a GroupMatch with ``name=None`` when nothing clears the confidence threshold -
    callers should route that to the review queue with a "create new group" option rather
    than treating it as an error (see docs/development/architecture.md, section 3).
    """

    lowered = text.lower()
    best_name: str | None = None
    best_score = 0

    for group_name in group_names:
        if group_name.lower() in lowered:
            return GroupMatch(name=group_name, confidence=1.0, reason=f"Exact match on group name '{group_name}'")

        score = fuzz.partial_ratio(group_name.lower(), lowered)
        if score > best_score:
            best_name, best_score = group_name, score

    if best_name is not None and best_score >= _FUZZY_MATCH_THRESHOLD:
        return GroupMatch(
            name=best_name,
            confidence=best_score / 100,
            reason=f"Fuzzy match on group name '{best_name}' (score={best_score})",
        )

    return GroupMatch(name=None, confidence=0.0, reason="No known group name found in document text")
