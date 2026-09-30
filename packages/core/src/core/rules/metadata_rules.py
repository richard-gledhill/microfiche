"""Filename-pattern based classification rules, loaded from filing_rules.yaml."""

from __future__ import annotations

import fnmatch

from core.models.classification import CategoryMatch

_FILENAME_MATCH_CONFIDENCE = 0.95
# Todo: move to config


def match_by_filename(file_name: str, rules: list[dict[str, str]]) -> CategoryMatch:
    """Match a filename against glob-style filing rules,
    e.g. ``{"pattern": "requirements*.docx", "category": "01 Requirements"}``."""

    for rule in rules:
        pattern = rule.get("pattern", "")
        category = rule.get("category")
        if pattern and category and fnmatch.fnmatch(file_name.lower(), pattern.lower()):
            return CategoryMatch(
                name=category,
                confidence=_FILENAME_MATCH_CONFIDENCE,
                reason=f"Filename matched rule pattern '{pattern}'",
            )
    return CategoryMatch(name=None, confidence=0.0, reason="No filename rule matched")
