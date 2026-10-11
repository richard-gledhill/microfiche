"""Filename-pattern based classification rules, from the ``rules`` in the library file."""

from __future__ import annotations

import fnmatch

from core.models.classification import CategoryMatch


def match_by_filename(file_name: str, rules: list[dict[str, str]], *, confidence: float) -> CategoryMatch:
    """Match a filename against glob-style filing rules.

    Args:
        file_name: The file name to match, case-insensitively.
        rules: Filing rules, each like ``{"pattern": "requirements*.docx", "category": "01 Requirements"}``.
        confidence: The confidence of a match.

    Returns:
        The category of the first rule whose pattern matches, or a match with ``name=None``
        if no rule matched.
    """

    for rule in rules:
        pattern = rule.get("pattern", "")
        category = rule.get("category")
        if pattern and category and fnmatch.fnmatch(file_name.lower(), pattern.lower()):
            return CategoryMatch(
                name=category,
                confidence=confidence,
                reason=f"Filename matched rule pattern '{pattern}'",
            )
    return CategoryMatch(name=None, confidence=0.0, reason="No filename rule matched")
