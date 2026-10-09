"""Stage 2 classification: which category within a known group does a document belong to."""

from __future__ import annotations

import re

from core.models.classification import CategoryMatch

_LEADING_ORDER_PREFIX_RE = re.compile(r"^\d+\s*")


def _normalize(category_name: str) -> str:
    """Strip a leading ordering prefix like "01 " so "01 Requirements" matches on "requirements"."""

    return _LEADING_ORDER_PREFIX_RE.sub("", category_name).strip().lower()


def match_category(
    text: str,
    category_names: list[str],
    hints: dict[str, list[str]],
    *,
    name_confidence: float,
    hint_confidence: float,
) -> CategoryMatch:
    """Match ``text`` against a group's existing category names, falling back to keyword hints.

    Args:
        text: The text to be analyzed for matching.
        category_names: The group's existing category names.
        hints: Keywords per category name, used when the category name itself doesn't appear.
        name_confidence: The confidence of a match on a category's name.
        hint_confidence: The confidence of a match on a keyword hint.

    Returns:
        The matching category with its confidence and the reason for it, or a match with
        ``name=None`` when neither a name nor a hint matched.
    """

    lowered = text.lower()

    for category_name in category_names:
        if _normalize(category_name) in lowered:
            return CategoryMatch(
                name=category_name,
                confidence=name_confidence,
                reason=f"Category name '{category_name}' found in document text",
            )

    for category_name in category_names:
        for keyword in hints.get(category_name, []):
            if keyword.lower() in lowered:
                return CategoryMatch(
                    name=category_name,
                    confidence=hint_confidence,
                    reason=f"Keyword hint '{keyword}' matched for category '{category_name}'",
                )

    return CategoryMatch(name=None, confidence=0.0, reason="No category keyword or name matched")
