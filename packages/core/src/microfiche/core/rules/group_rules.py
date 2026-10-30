"""Stage 1 classification: which library group (level 1, e.g. a project) does a document belong to."""

from __future__ import annotations

from microfiche.core.models.classification import GroupMatch
from microfiche.core.rules.ambiguity import Candidate, choose
from microfiche.core.rules.normalise import contains_words, normalise_for_matching
from rapidfuzz import fuzz


def match_group(
    text: str,
    group_names: list[str],
    *,
    fuzzy_threshold: int,
    normalise: bool = True,
    margin: float = 0.0,
) -> GroupMatch:
    """Match ``text`` against known group names by whole words, then fuzzy match.

    Every group the text names is a candidate: a group name found in the text scores 1.0, and otherwise a fuzzy match
    scores its fuzzy score if that clears the fuzzy threshold. The best candidate wins unless another is within
    ``margin`` of it, in which case the document names several groups about equally and none is chosen.

    Callers should route a result with ``name=None`` to the review queue with a "create new
    group" option rather than treating it as an error (see docs/development/architecture/overview.md,
    section 3).

    Args:
        text: The text to be analyzed for matching.
        group_names: The group names to match against the text.
        fuzzy_threshold: The lowest fuzzy score (0 to 100) that counts as a match.
        normalise: Compare names and text through ``normalise_for_matching``, so ``R&D`` finds ``R and D``, and
            count only whole words. Off compares them as lowercased substrings, as written.
        margin: How close (0 to 1) the runner-up may be to the best before none is chosen.

    Returns:
        The best matching group with its confidence and the reason for it; a match with ``name=None`` and the
        close ``candidates`` when the evidence is too close to call; or a match with ``name=None`` when nothing
        clears the confidence threshold.

    Todo:
        - Need to review the group_name match. Consider as config option to sort by extracted title and keywords.
    """

    lowered = normalise_for_matching(text) if normalise else text.lower()
    # Scores are rounded to a whole number before they are compared with the threshold, so 84.6 counts as 85.
    # A raw score below the threshold less one cannot round up to it, so RapidFuzz may stop early on those.
    cutoff = max(0, fuzzy_threshold - 1)
    candidates: list[Candidate] = []

    for group_name in group_names:
        wanted = normalise_for_matching(group_name, folder_name=True) if normalise else group_name.lower()
        if not wanted:
            continue
        if contains_words(lowered, wanted) if normalise else wanted in lowered:
            candidates.append(Candidate(group_name, 1.0, f"Exact match on group name '{group_name}'", wanted))
            continue

        alignment = fuzz.partial_ratio_alignment(wanted, lowered, score_cutoff=cutoff)
        if alignment is None:
            continue
        if normalise and not _on_word_boundaries(lowered, alignment.dest_start, alignment.dest_end):
            continue
        score = round(alignment.score)
        if score >= fuzzy_threshold:
            reason = f"Fuzzy match on group name '{group_name}' (score={score})"
            candidates.append(Candidate(group_name, score / 100, reason, wanted))

    if any(c.confidence == 1.0 for c in candidates):
        # A group named exactly settles it: siblings that merely look like that name (`Project X`, `Project Y`) are
        # a property of the folder names, not evidence from the document.
        candidates = [c for c in candidates if c.confidence == 1.0]
    choice = choose(candidates, margin)
    if choice.winner is not None:
        return GroupMatch(name=choice.winner.name, confidence=choice.winner.confidence, reason=choice.winner.reason)
    if choice.ambiguous:
        return GroupMatch(
            name=None,
            confidence=0.0,
            reason=choice.reason("groups"),
            candidates=tuple(c.name for c in choice.close),
        )
    return GroupMatch(name=None, confidence=0.0, reason="No known group name found in document text")


def _on_word_boundaries(text: str, start: int, end: int) -> bool:
    """Whether ``text[start:end]`` begins and ends at a word edge, so it is not part of a longer word.

    The aligned window is as long as the name, so a near-miss can leave a space at either end; that space is the edge.
    """

    while start < end and text[start] == " ":
        start += 1
    while end > start and text[end - 1] == " ":
        end -= 1
    return (start == 0 or text[start - 1] == " ") and (end >= len(text) or text[end] == " ")
