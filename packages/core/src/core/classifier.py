"""Two-stage (group, then category) classification, with an optional AI fallback."""

from __future__ import annotations

from collections import Counter

from core.ai.llm_classifier import LLMClassifier
from core.models.category import Taxonomy
from core.models.classification import ClassificationResult
from core.models.unit import SortableUnit
from core.rules.confidence import combine_confidence
from core.rules.rules_engine import RulesEngine

CONFIDENCE_THRESHOLD = 0.6


class Classifier:
    """Combines the deterministic RulesEngine with an optional AI fallback for low-confidence cases."""

    def __init__(self, rules_engine: RulesEngine, ai_classifier: LLMClassifier | None = None) -> None:
        self._rules_engine = rules_engine
        self._ai_classifier = ai_classifier

    def classify_document(self, file_name: str, text: str, taxonomy: Taxonomy) -> ClassificationResult:
        result = self._rules_engine.classify(file_name, text, taxonomy)
        if result.overall_confidence >= CONFIDENCE_THRESHOLD or self._ai_classifier is None:
            return result

        group = self._ai_classifier.resolve_group(text, taxonomy)
        category = (
            self._ai_classifier.resolve_category(text, group.name, taxonomy)
            if group.name is not None
            else result.category
        )
        return ClassificationResult(
            group=group,
            category=category,
            overall_confidence=combine_confidence(group.confidence, category.confidence),
            classified_by="ai_fallback",
        )

    def classify_unit(self, unit: SortableUnit, taxonomy: Taxonomy) -> ClassificationResult:
        """Classify a unit. A single-file unit is classified directly; a folder unit is classified
        by the dominant (group, category) pair voted across all the documents inside it (see the
        "folder-as-unit" decision in docs/prd/20260907_microfiche_architecture_v2.md)."""

        per_document = [
            self.classify_document(document.file_name, document.content, taxonomy) for document in unit.documents
        ]
        if len(per_document) == 1:
            return per_document[0]

        pair_votes = Counter(
            (result.group.name, result.category.name) for result in per_document if result.group.name is not None
        )
        if not pair_votes:
            # No document in the folder resolved a group at all - surface the first result's
            # reasoning so the review queue has something concrete to show the user.
            return per_document[0]

        (group_name, category_name), _ = pair_votes.most_common(1)[0]
        return next(
            result
            for result in per_document
            if result.group.name == group_name and result.category.name == category_name
        )
