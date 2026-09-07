"""Ties together filename, group, and keyword rules into a single deterministic classification pass."""

from __future__ import annotations

from core.models.category import Taxonomy
from core.models.classification import CategoryMatch, ClassificationResult, GroupMatch
from core.rules.confidence import combine_confidence
from core.rules.group_rules import match_group
from core.rules.keyword_rules import match_category
from core.rules.metadata_rules import match_by_filename


class RulesEngine:
    """Deterministic (no-AI) classifier: resolves group then category using rules only."""

    def __init__(self, category_hints: dict[str, list[str]], filing_rules: list[dict[str, str]]) -> None:
        self._category_hints = category_hints
        self._filing_rules = filing_rules

    def resolve_group(self, text: str, taxonomy: Taxonomy) -> GroupMatch:
        return match_group(text, taxonomy.group_names)

    def resolve_category(self, file_name: str, text: str, group: str, taxonomy: Taxonomy) -> CategoryMatch:
        by_filename = match_by_filename(file_name, self._filing_rules)
        if by_filename.name is not None:
            return by_filename
        return match_category(text, taxonomy.categories_for(group), self._category_hints)

    def classify(self, file_name: str, text: str, taxonomy: Taxonomy) -> ClassificationResult:
        group_match = self.resolve_group(text, taxonomy)
        if group_match.name is None:
            category_match = CategoryMatch(name=None, confidence=0.0, reason="Group unresolved")
        else:
            category_match = self.resolve_category(file_name, text, group_match.name, taxonomy)

        overall = combine_confidence(group_match.confidence, category_match.confidence)
        return ClassificationResult(
            group=group_match,
            category=category_match,
            overall_confidence=overall,
            classified_by="rules_engine",
        )
