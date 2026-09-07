"""Stage 2 classification: which category within a known group does a document belong to."""

from __future__ import annotations

import re

from core.models.classification import CategoryMatch

_HINT_MATCH_CONFIDENCE = 0.75
_NAME_MATCH_CONFIDENCE = 0.9
_LEADING_ORDER_PREFIX_RE = re.compile(r"^\d+\s*")


def _normalize(category_name: str) -> str:
    """Strip a leading ordering prefix like "01 " so "01 Requirements" matches on "requirements"."""

    return _LEADING_ORDER_PREFIX_RE.sub("", category_name).strip().lower()


def match_category(text: str, category_names: list[str], hints: dict[str, list[str]]) -> CategoryMatch:
    """Match ``text`` against a group's existing category names, using ``hints`` (category -> keywords)
    as a fallback when the category name itself doesn't appear."""

    lowered = text.lower()

    for category_name in category_names:
        if _normalize(category_name) in lowered:
            return CategoryMatch(
                name=category_name,
                confidence=_NAME_MATCH_CONFIDENCE,
                reason=f"Category name '{category_name}' found in document text",
            )

    for category_name in category_names:
        for keyword in hints.get(category_name, []):
            if keyword.lower() in lowered:
                return CategoryMatch(
                    name=category_name,
                    confidence=_HINT_MATCH_CONFIDENCE,
                    reason=f"Keyword hint '{keyword}' matched for category '{category_name}'",
                )

    return CategoryMatch(name=None, confidence=0.0, reason="No category keyword or name matched")
