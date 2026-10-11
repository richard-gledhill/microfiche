"""Two-stage (group, then category) classification over pluggable resolvers.

``Classifier`` owns the whole decision: it asks a primary resolver (the deterministic rules) for
each stage, optionally falls back to a second resolver (the AI) for a stage the first couldn't
answer confidently, checks every answer against the library's taxonomy, and says whether the
result is confident enough to file. The resolvers only propose; they don't decide.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from typing import Protocol, TypeVar

from core.library.library import Library
from core.models.category import Taxonomy
from core.models.classification import CategoryMatch, ClassificationResult, GroupMatch
from core.models.document import Document
from core.models.unit import SortableUnit
from core.rules.confidence import DEFAULT_CONFIDENCE_THRESHOLD, combine_confidence
from core.rules.rules_engine import RulesEngine

# region Constants and types

Match = TypeVar("Match", GroupMatch, CategoryMatch)


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
    """

    def __init__(
        self,
        rules: Resolver,
        fallback: Resolver | None = None,
        *,
        threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        self._rules = rules
        self._fallback = fallback
        self._threshold = threshold

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
        )

    @property
    def threshold(self) -> float:
        """The confidence a result must reach to be ``confident``."""

        return self._threshold

    def classify_document(self, document: Document, taxonomy: Taxonomy) -> ClassificationResult:
        """Classify one document: resolve its group, then its category within that group.

        Args:
            document: The document to classify.
            taxonomy: The library's groups and categories.

        Returns:
            The classification, which is ``confident`` only if both stages resolved to existing
            folders and the overall confidence reaches the threshold.
        """

        group, group_source = self._resolve(lambda r: _known_group(r.resolve_group(document, taxonomy), taxonomy))
        if group.name is None:
            category = CategoryMatch(name=None, confidence=0.0, reason="Group unresolved")
            category_source = self._rules
        else:
            group_name = group.name
            category, category_source = self._resolve(
                lambda r: _known_category(r.resolve_category(document, group_name, taxonomy), group_name, taxonomy)
            )

        overall = combine_confidence(group.confidence, category.confidence)
        return ClassificationResult(
            group=group,
            category=category,
            overall_confidence=overall,
            classified_by=self._label(group_source, category_source),
            confident=group.name is not None and category.name is not None and overall >= self._threshold,
        )

    def classify_unit(self, unit: SortableUnit, taxonomy: Taxonomy) -> ClassificationResult:
        """Classify a unit: a file directly, a folder by the dominant pair across its documents.

        A single-file unit is classified directly. A folder unit is classified by the dominant
        (group, category) pair voted across all the documents inside it (see the "folder-as-unit"
        decision in docs/development/architecture.md).

        Each document whose group resolved casts one vote. The pair with the most votes wins, and
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
            return _nothing_to_classify(unit)

        per_document = [self.classify_document(document, taxonomy) for document in unit.documents]
        if len(per_document) == 1:
            return per_document[0]

        pair_votes = Counter((result.group.name, result.category.name) for result in per_document if result.group.name)
        if not pair_votes:
            # No document in the folder resolved a group at all - surface the first result's
            # reasoning so the review queue has something concrete to show the user.
            return per_document[0]

        ranked = pair_votes.most_common()
        leaders = [(pair, votes) for pair, votes in ranked if votes == ranked[0][1]]
        if len(leaders) > 1:
            return _tied_vote(leaders)

        (group_name, category_name), _ = leaders[0]
        return max(
            (r for r in per_document if (r.group.name, r.category.name) == (group_name, category_name)),
            key=lambda result: result.overall_confidence,
        )

    def _resolve(self, ask: Callable[[Resolver], Match]) -> tuple[Match, Resolver]:
        """Ask the primary resolver; if it isn't confident, ask the fallback.

        Args:
            ask: Puts the stage's question to a resolver.

        Returns:
            The answer used and the resolver it came from.
        """

        answer = ask(self._rules)
        if self._is_confident(answer) or self._fallback is None:
            return answer, self._rules
        fallback_answer = ask(self._fallback)
        if fallback_answer.name is not None:
            return fallback_answer, self._fallback
        return answer, self._rules

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


def _nothing_to_classify(unit: SortableUnit) -> ClassificationResult:
    """An unresolved result for a unit none of whose documents could be read."""

    reason = (
        "; ".join(f"Could not read '{u.file_path.name}': {u.reason}" for u in unit.unreadable)
        or "No readable documents"
    )
    return ClassificationResult(
        group=GroupMatch(name=None, confidence=0.0, reason=reason),
        category=CategoryMatch(name=None, confidence=0.0, reason=reason),
        overall_confidence=0.0,
        classified_by="unreadable",
        confident=False,
    )


def _tied_vote(leaders: Sequence[tuple[tuple[str | None, str | None], int]]) -> ClassificationResult:
    """An unresolved result explaining which (group, category) pairs tied for the most votes."""

    breakdown = ", ".join(
        f"{group}/{category or '(no category)'} ({votes} documents)" for (group, category), votes in leaders
    )
    reason = f"Documents in this folder disagree: {breakdown}"
    return ClassificationResult(
        group=GroupMatch(name=None, confidence=0.0, reason=reason),
        category=CategoryMatch(name=None, confidence=0.0, reason=reason),
        overall_confidence=0.0,
        classified_by="folder_vote",
        confident=False,
    )


# endregion
