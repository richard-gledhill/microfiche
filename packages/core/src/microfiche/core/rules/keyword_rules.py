"""Stage 2 classification: which category within a known group does a document belong to."""

from __future__ import annotations

import re

from microfiche.core.models.classification import CategoryMatch, GroupMatch
from microfiche.core.rules.ambiguity import Candidate, choose
from microfiche.core.rules.normalise import contains_words, normalise_for_matching

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
    normalise: bool = True,
    margin: float = 0.0,
) -> CategoryMatch:
    """Match ``text`` against a group's existing category names and keyword hints.

    Each category the text gives evidence for is a candidate, scored by its best evidence: ``name_confidence`` if its
    name appears, else ``hint_confidence`` if one of its hints does. The best candidate wins unless another is within
    ``margin`` of it, in which case none is chosen.

    Args:
        text: The text to be analyzed for matching.
        category_names: The group's existing category names.
        hints: Keywords per category name, used when the category name itself doesn't appear.
        name_confidence: The confidence of a match on a category's name.
        hint_confidence: The confidence of a match on a keyword hint.
        normalise: Compare names, hints and text through ``normalise_for_matching`` and count only whole words. Off
            compares them lowercased, as written.
        margin: How close (0 to 1) the runner-up may be to the best before none is chosen.

    Returns:
        The matching category with its confidence and the reason for it; a match with ``name=None`` and the close
        ``candidates`` when the evidence is too close to call; or a match with ``name=None`` when neither a name nor
        a hint matched.
    """

    lowered = _prepare_text(text, normalise)
    candidates: list[Candidate] = []

    for category_name in category_names:
        wanted = _prepare_name(category_name, normalise)
        if _found(wanted, lowered, normalise):
            reason = f"Category name '{category_name}' found in document text"
            candidates.append(Candidate(category_name, name_confidence, reason, wanted))
            continue
        for keyword in hints.get(category_name, []):
            wanted = _prepare_hint(keyword, normalise)
            if _found(wanted, lowered, normalise):
                reason = f"Keyword hint '{keyword}' matched for category '{category_name}'"
                candidates.append(Candidate(category_name, hint_confidence, reason, wanted))
                break

    choice = choose(candidates, margin)
    if choice.winner is not None:
        return CategoryMatch(name=choice.winner.name, confidence=choice.winner.confidence, reason=choice.winner.reason)
    if choice.ambiguous:
        return CategoryMatch(
            name=None,
            confidence=0.0,
            reason=choice.reason("categories"),
            candidates=tuple(c.name for c in choice.close),
        )
    return CategoryMatch(name=None, confidence=0.0, reason="No category keyword or name matched")


def match_group_hints(
    text: str, hints: dict[str, list[str]], *, confidence: float, normalise: bool = True
) -> GroupMatch:
    """Match ``text`` against the keyword hints of a flat library's groups.

    A flat library has only its group folders to match on, so a group's name (see ``match_group``) is tried
    first and these hints are the next best thing.

    Args:
        text: The text to be analyzed for matching.
        hints: Keywords per group name.
        confidence: The confidence of a match on a keyword hint.
        normalise: Compare hints and text through ``normalise_for_matching``. Off compares them lowercased.

    Returns:
        The group one of whose hints appears in the text, or a match with ``name=None`` if none did. If hints of
        more than one group appear there is no basis to choose, so the match is unresolved and says which groups.
    """

    lowered = _prepare_text(text, normalise)
    found = {
        group_name: keyword
        for group_name, keywords in hints.items()
        for keyword in keywords
        if _found(_prepare_hint(keyword, normalise), lowered, normalise)
    }
    if len(found) > 1:
        which = ", ".join(f"'{group}' ('{keyword}')" for group, keyword in found.items())
        return GroupMatch(name=None, confidence=0.0, reason=f"Keyword hints of several groups matched: {which}")
    for group_name, keyword in found.items():
        return GroupMatch(
            name=group_name,
            confidence=confidence,
            reason=f"Keyword hint '{keyword}' matched for group '{group_name}'",
        )
    return GroupMatch(name=None, confidence=0.0, reason="No group keyword or name matched")


def _prepare_text(text: str, normalise: bool) -> str:
    return normalise_for_matching(text) if normalise else text.lower()


def _prepare_name(name: str, normalise: bool) -> str:
    return normalise_for_matching(name, folder_name=True) if normalise else _normalize(name)


def _prepare_hint(keyword: str, normalise: bool) -> str:
    return normalise_for_matching(keyword) if normalise else keyword.lower()


def _found(wanted: str, text: str, normalise: bool) -> bool:
    """Whether ``wanted`` is in ``text``: as whole words when normalising, as a plain substring when not."""

    if not wanted:
        return False
    return contains_words(text, wanted) if normalise else wanted in text
