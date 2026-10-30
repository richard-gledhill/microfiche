"""Two-stage (group, then category) classification over pluggable resolvers.

``Classifier`` owns the whole decision: it asks a primary resolver (the deterministic rules) for
each stage, optionally falls back to a second resolver (the AI) for a stage the first couldn't
answer confidently, checks every answer against the library's taxonomy, and says whether the
result is confident enough to file. The resolvers only propose; they don't decide.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar, runtime_checkable

from microfiche.core.library.library import Library
from microfiche.core.models.category import Taxonomy
from microfiche.core.models.classification import CONFIRMED_BY_AI, CategoryMatch, ClassificationResult, GroupMatch
from microfiche.core.models.document import Document
from microfiche.core.models.unit import SortableUnit
from microfiche.core.rules.confidence import DEFAULT_CONFIDENCE_THRESHOLD, combine_confidence
from microfiche.core.rules.rules_engine import RulesEngine

# region Constants and types

Match = TypeVar("Match", GroupMatch, CategoryMatch)

_logger = logging.getLogger(__name__)


class Resolver(Protocol):
    """Proposes a group, or a category within a group, for a document.

    Attributes:
        name: Identifies the resolver in ``ClassificationResult.classified_by``.
    """

    name: str

    def resolve_group(self, document: Document, taxonomy: Taxonomy) -> GroupMatch:
        """Propose which group ``document`` belongs to (``name=None`` if it can't tell)."""

        ...

    def resolve_category(self, document: Document, group: str, taxonomy: Taxonomy) -> CategoryMatch:
        """Propose which category of ``group`` ``document`` belongs to (``name=None`` if it can't tell)."""

        ...


@runtime_checkable
class _CanFail(Protocol):
    """A resolver that can stop answering part-way through a run (the AI), saying why."""

    @property
    def failure(self) -> str | None: ...


@dataclass
class VerificationStats:
    """How many rules answers the fallback was asked to check (``[ai] verify_below``), and what it said.

    Attributes:
        checked: Answers the fallback gave an opinion on.
        confirmed: Of those, the ones it agreed with.
        overruled: Of those, the ones it disagreed with, so the unit is held for review.
    """

    checked: int = 0
    confirmed: int = 0
    overruled: int = 0


# endregion


# region Public API


class Classifier:
    """Decides where a document, or a whole folder, belongs.

    For each stage - group first, then category within the resolved group - the primary resolver
    is asked. If its answer is missing or below the confidence threshold and a fallback resolver
    was given, the fallback is asked too, and its answer is used if it names something; otherwise
    the primary's answer stands, so a weak suggestion is never replaced by nothing. A group or
    category that isn't in the taxonomy is treated as unresolved, whoever proposed it.

    A folder is classified document by document; the pair of (group, category) most documents
    voted for wins. If the top vote is tied, the folder is left unresolved rather than guessed.

    Args:
        rules: The primary resolver, asked first for every stage.
        fallback: An optional second resolver, asked only for stages the primary can't answer
            confidently.
        threshold: How confident a result must be to count as ``confident``.
        file_in_empty_groups: Whether a group with no category folders is itself the destination (see
            ``[sorting] file_in_empty_groups``). Its category is then not asked for and the result has none, as in a
            flat library.
        verify_below: With a fallback, a primary answer that would file but scores below this is checked by the fallback
            (``[ai] verify_below``). 0 checks nothing.

    Attributes:
        verification: How many answers were checked, confirmed and overruled so far.
    """

    def __init__(
        self,
        rules: Resolver,
        fallback: Resolver | None = None,
        *,
        threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        file_in_empty_groups: bool = False,
        verify_below: float = 0.0,
    ) -> None:
        self._rules = rules
        self._fallback = fallback
        self._threshold = threshold
        self._file_in_empty_groups = file_in_empty_groups
        self._verify_below = verify_below
        self.verification = VerificationStats()

    @classmethod
    def from_library(cls, library: Library, fallback: Resolver | None = None) -> Classifier:
        """Build the default classifier for a library.

        Wires the rules engine from the library file's hints and filing rules and the config's
        signal strengths, an optional fallback resolver, and the library's confidence threshold.

        Args:
            library: The library to classify for.
            fallback: An optional second resolver, such as the AI classifier.

        Returns:
            A ``Classifier`` configured for the library.
        """

        config = library.config
        return cls(
            RulesEngine(library.library_file, config.classification),
            fallback,
            threshold=config.classification.confidence_threshold,
            file_in_empty_groups=config.sorting.file_in_empty_groups,
            verify_below=config.ai.verify_below,
        )

    def classify_document(self, document: Document, taxonomy: Taxonomy) -> ClassificationResult:
        """Classify one document: resolve its group, then its category within that group.

        Args:
            document: The document to classify.
            taxonomy: The library's groups and categories.

        Returns:
            The classification, which is ``confident`` only if both stages resolved to existing
            folders and the overall confidence reaches the threshold.
        """

        group, group_sources, group_overruled = self._resolve(
            "group", lambda r: _known_group(r.resolve_group(document, taxonomy), taxonomy)
        )
        category: CategoryMatch | None
        category_overruled = None
        if taxonomy.is_flat or self._is_leaf(group, taxonomy):
            category, category_sources = None, group_sources  # nothing below the group to choose
        elif group.name is None:
            category = CategoryMatch(name=None, confidence=0.0, reason="Group unresolved")
            category_sources = [self._rules]
        else:
            group_name = group.name
            category, category_sources, category_overruled = self._resolve(
                "category",
                lambda r: _known_category(r.resolve_category(document, group_name, taxonomy), group_name, taxonomy),
            )

        overall = group.confidence if category is None else combine_confidence(group.confidence, category.confidence)
        result = ClassificationResult(
            group=group,
            category=category,
            overall_confidence=overall,
            classified_by=self._label(*group_sources, *category_sources),
            confident=_resolved(group, category) and overall >= self._threshold,
        )
        disagreements = [why for why in (group_overruled, category_overruled) if why]
        if disagreements:
            result = result.held("; ".join(disagreements)).model_copy(update={"ai_overruled": True})

        _logger.debug(
            "%s: group %s (%.2f, %s); category %s (%.2f, %s); by %s",
            document.file_name,
            group.name,
            group.confidence,
            group.reason,
            category.name if category else None,
            category.confidence if category else 0.0,
            category.reason if category else "no categories in a flat library",
            result.classified_by,
        )

        return result

    def classify_unit(self, unit: SortableUnit, taxonomy: Taxonomy) -> ClassificationResult:
        """Classify a unit: a file directly, a folder by the dominant pair across its documents.

        A single-file unit is classified directly. A folder unit is classified by the dominant
        (group, category) pair voted across all the documents inside it (see the "folder-as-unit"
        decision in docs/development/architecture/overview.md).

        Each document whose group resolved casts one vote, unless the evidence for it was too close to call between
        several folders (``ClassificationResult.ambiguous``): then it abstains. The pair with the most votes wins, and
        the winning pair's most confident document represents the folder. If two or more pairs
        share the top vote the folder is unresolved, with a reason listing the disagreement.

        A unit with no readable document is left unresolved, with the reason it couldn't be read.

        Args:
            unit: The file or folder to classify.
            taxonomy: The library's groups and categories.

        Returns:
            The unit's classification.
        """

        if not unit.documents:
            return _nothing_to_classify(unit, flat=taxonomy.is_flat)

        per_document = [self.classify_document(document, taxonomy) for document in unit.documents]
        if len(per_document) == 1:
            return per_document[0]

        pair_votes = Counter(
            _vote(result)
            for result in per_document
            if result.group.name and not result.ambiguous and not result.ai_overruled
        )
        if not pair_votes:
            # No document in the folder resolved a group, or all were ambiguous or overruled - surface the first result's
            # reasoning so the review queue has something concrete to show the user.
            return per_document[0]

        ranked = pair_votes.most_common()
        leaders = [(pair, votes) for pair, votes in ranked if votes == ranked[0][1]]
        if len(leaders) > 1:
            return _tied_vote(leaders, flat=taxonomy.is_flat)

        winner, _ = leaders[0]
        return max(
            (r for r in per_document if _vote(r) == winner),
            key=lambda result: result.overall_confidence,
        )

    def _resolve(self, stage: str, ask: Callable[[Resolver], Match]) -> tuple[Match, list[Resolver], str | None]:
        """Ask the primary resolver; if it isn't confident, ask the fallback, or if it is only just, have it check.

        Args:
            stage: ``"group"`` or ``"category"``, for the reason a check gives.
            ask: Puts the stage's question to a resolver.

        Returns:
            The answer used, the resolvers it came from, and, if the fallback was asked to check a primary answer and
            picked something else, a sentence saying so (otherwise ``None``).
        """

        answer = ask(self._rules)
        if self._fallback is None:
            return answer, [self._rules], None
        if not self._is_confident(answer):
            fallback_answer = ask(self._fallback)
            if fallback_answer.name is not None:
                return fallback_answer, [self._fallback], None
            return answer, [self._rules], None
        if answer.confidence >= self._verify_below:
            return answer, [self._rules], None
        return self._verify(stage, answer, ask, self._fallback)

    def _verify(
        self, stage: str, answer: Match, ask: Callable[[Resolver], Match], fallback: Resolver
    ) -> tuple[Match, list[Resolver], str | None]:
        """Have ``fallback`` check ``answer``: the same folder confirms it, anything else holds the unit.

        If the fallback has stopped answering, the answer stands as the primary gave it and is not counted.
        """

        second = ask(fallback)
        if isinstance(fallback, _CanFail) and fallback.failure is not None:
            return answer, [self._rules], None
        self.verification.checked += 1
        if second.name == answer.name:
            self.verification.confirmed += 1
            confirmed = answer.model_copy(update={"reason": f"{answer.reason}; {CONFIRMED_BY_AI}"})
            return confirmed, [self._rules, fallback], None
        self.verification.overruled += 1
        chose = f"it chose '{second.name}'" if second.name is not None else "it found no match"
        return answer, [self._rules], f"the AI disagrees about the {stage}: {chose}"

    def _is_leaf(self, group: GroupMatch, taxonomy: Taxonomy) -> bool:
        """Whether the group resolved to a folder with no categories that this library files straight into."""

        return self._file_in_empty_groups and group.name is not None and taxonomy.is_leaf(group.name)

    def _is_confident(self, match: GroupMatch | CategoryMatch) -> bool:
        return match.name is not None and match.confidence >= self._threshold

    def _label(self, *sources: Resolver) -> str:
        """Names of the resolvers that decided a stage, primary first (e.g. ``rules_engine+ai_fallback``)."""

        used = [r for r in (self._rules, self._fallback) if r is not None and any(r is source for source in sources)]
        return "+".join(resolver.name for resolver in used)


# endregion


# region Helpers


def _known_group(match: GroupMatch, taxonomy: Taxonomy) -> GroupMatch:
    """``match``, or an unresolved match if it names a group that isn't in the taxonomy."""

    if match.name is None or match.name in taxonomy.group_names:
        return match
    return GroupMatch(name=None, confidence=0.0, reason=f"{match.reason}; but '{match.name}' is not an existing group")


def _known_category(match: CategoryMatch, group: str, taxonomy: Taxonomy) -> CategoryMatch:
    """``match``, or an unresolved match if it names a category that isn't in ``group``."""

    if match.name is None or match.name in taxonomy.categories_for(group):
        return match
    return CategoryMatch(
        name=None,
        confidence=0.0,
        reason=f"{match.reason}; but '{match.name}' is not an existing category of '{group}'",
    )


def _resolved(group: GroupMatch, category: CategoryMatch | None) -> bool:
    """Whether every level the library has was resolved to a name (a flat library has no category to resolve)."""

    return group.name is not None and (category is None or category.name is not None)


def _vote(result: ClassificationResult) -> tuple[str | None, str | None]:
    """What a document votes for: its group and, in a library with categories, its category."""

    return result.group.name, result.category.name if result.category else None


def _nothing_to_classify(unit: SortableUnit, *, flat: bool) -> ClassificationResult:
    """An unresolved result for a unit none of whose documents could be read."""

    reason = (
        "; ".join(f"Could not read '{u.file_path.name}': {u.reason}" for u in unit.unreadable)
        or "No readable documents"
    )
    return ClassificationResult(
        group=GroupMatch(name=None, confidence=0.0, reason=reason),
        category=None if flat else CategoryMatch(name=None, confidence=0.0, reason=reason),
        overall_confidence=0.0,
        classified_by="unreadable",
        confident=False,
    )


def _tied_vote(leaders: Sequence[tuple[tuple[str | None, str | None], int]], *, flat: bool) -> ClassificationResult:
    """An unresolved result explaining which (group, category) pairs tied for the most votes."""

    breakdown = ", ".join(
        f"{group} ({votes} documents)" if flat else f"{group}/{category or '(no category)'} ({votes} documents)"
        for (group, category), votes in leaders
    )
    reason = f"Documents in this folder disagree: {breakdown}"
    return ClassificationResult(
        group=GroupMatch(name=None, confidence=0.0, reason=reason),
        category=None if flat else CategoryMatch(name=None, confidence=0.0, reason=reason),
        overall_confidence=0.0,
        classified_by="folder_vote",
        confident=False,
    )


# endregion
