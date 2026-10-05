"""Maps freely extracted tag candidates onto a library's canonical TagIndex.md vocabulary."""

from __future__ import annotations

from typing import Literal

from thefuzz import process

from core.obsidian.tag_index import TagIndex

TagMode = Literal["suggest", "strict", "off"]

_FUZZY_MATCH_THRESHOLD = 90


def map_tags(candidate_tags: list[str], tag_index: TagIndex, mode: TagMode) -> list[str]:
    """Resolve ``candidate_tags`` against ``tag_index``'s canonical vocabulary per ``mode``.

    - "off": candidates are returned unchanged; TagIndex is never consulted or updated.
    - "strict": only candidates with a close canonical match are kept; everything else is dropped.
    - "suggest" (the default - see the ADR): a candidate with a close canonical match is
      normalized to it; anything else is still applied to the document, and appended to
      TagIndex.md's Proposed section for later review.

    Args:
        candidate_tags: The tags extracted from a document.
        tag_index: The library's tag vocabulary; proposed tags are added to it in "suggest" mode.
        mode: How to treat candidates with no close canonical match.

    Returns:
        The tags to apply to the document.
    """

    if mode == "off":
        return candidate_tags

    resolved: list[str] = []
    canonical = sorted(tag_index.canonical_tags)
    for candidate in candidate_tags:
        match = process.extractOne(candidate, canonical) if canonical else None
        if match is not None and match[1] >= _FUZZY_MATCH_THRESHOLD:
            resolved.append(match[0])
        elif mode == "suggest":
            tag_index.add_proposed(candidate)
            resolved.append(candidate)
        # mode == "strict" and no close match: drop the candidate entirely

    return resolved
