"""Filename-pattern based classification rules, from the ``rules`` in the library file."""

from __future__ import annotations

import fnmatch

from core.models.classification import CategoryMatch, GroupMatch


def match_by_filename(file_name: str, rules: list[dict[str, str]], *, confidence: float) -> CategoryMatch:
    """Match a filename against glob-style filing rules.

    Args:
        file_name: The file name to match, case-insensitively.
        rules: Filing rules, each like ``{"pattern": "requirements*.docx", "target": "01 Requirements"}``,
            where the target is the folder the rule files into.
        confidence: The confidence of a match.

    Returns:
        The category of the first rule whose pattern matches, or a match with ``name=None``
        if no rule matched.
    """

    target, reason = _first_match(file_name, rules)
    if target is None:
        return CategoryMatch(name=None, confidence=0.0, reason=reason)
    return CategoryMatch(name=target, confidence=confidence, reason=reason)


def match_group_by_filename(file_name: str, rules: list[dict[str, str]], *, confidence: float) -> GroupMatch:
    """Match a filename against the filing rules of a flat library, whose rules target groups.

    Args:
        file_name: The file name to match, case-insensitively.
        rules: Filing rules, each like ``{"pattern": "statement-*.pdf", "target": "Household"}``.
        confidence: The confidence of a match.

    Returns:
        The group of the first rule whose pattern matches, or a match with ``name=None`` if none did.
    """

    target, reason = _first_match(file_name, rules)
    if target is None:
        return GroupMatch(name=None, confidence=0.0, reason=reason)
    return GroupMatch(name=target, confidence=confidence, reason=reason)


def _first_match(file_name: str, rules: list[dict[str, str]]) -> tuple[str | None, str]:
    """The target of the first rule matching ``file_name`` and why, or ``None`` and the reason there is none."""

    for rule in rules:
        pattern = rule.get("pattern", "")
        target = rule.get("target")
        if pattern and target and fnmatch.fnmatch(file_name.lower(), pattern.lower()):
            return target, f"Filename matched rule pattern '{pattern}'"
    return None, "No filename rule matched"
