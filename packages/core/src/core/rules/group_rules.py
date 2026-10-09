"""Stage 1 classification: which library group (level 1, e.g. a project) does a document belong to."""

from __future__ import annotations

from thefuzz import fuzz

from core.models.classification import GroupMatch


def match_group(text: str, group_names: list[str], *, fuzzy_threshold: int) -> GroupMatch:
    """Match ``text`` against known group names by substring, then fuzzy match.

    A group name found in the lowercased text is an exact match. Otherwise the best fuzzy match
    is used if its score clears the fuzzy threshold.

    Callers should route a result with ``name=None`` to the review queue with a "create new
    group" option rather than treating it as an error (see docs/development/architecture.md,
    section 3).

    Args:
        text: The text to be analyzed for matching.
        group_names: The group names to match against the text.
        fuzzy_threshold: The lowest fuzzy score (0 to 100) that counts as a match.

    Returns:
        The best matching group with its confidence and the reason for it, or a match with
        ``name=None`` when nothing clears the confidence threshold.

    Todo:
        - Need to review the group_name match. Consider as config option to sort by extracted title and keywords.
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

    if best_name is not None and best_score >= fuzzy_threshold:
        return GroupMatch(
            name=best_name,
            confidence=best_score / 100,
            reason=f"Fuzzy match on group name '{best_name}' (score={best_score})",
        )

    return GroupMatch(name=None, confidence=0.0, reason="No known group name found in document text")
