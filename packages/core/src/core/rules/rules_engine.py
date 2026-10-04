"""The deterministic resolver: filename, group and keyword rules, with no AI involved."""

from __future__ import annotations

from core.models.category import Taxonomy
from core.models.classification import CategoryMatch, GroupMatch
from core.models.document import Document
from core.rules.group_rules import match_group
from core.rules.keyword_rules import match_category
from core.rules.metadata_rules import match_by_filename


class RulesEngine:
    """Resolver backed by rules only. Proposes a group by name match, and a category by filename
    rule first, then category name or keyword hint - all scoped to the group's existing categories.

    It only proposes: ``core.classifier.Classifier`` runs the two stages, decides what is
    confident, and enforces the taxonomy.
    """

    name: str = "rules_engine"

    def __init__(self, category_hints: dict[str, list[str]], filing_rules: list[dict[str, str]]) -> None:
        self._category_hints = category_hints
        self._filing_rules = filing_rules

    def resolve_group(self, document: Document, taxonomy: Taxonomy) -> GroupMatch:
        return match_group(document.content, taxonomy.group_names)

    def resolve_category(self, document: Document, group: str, taxonomy: Taxonomy) -> CategoryMatch:
        categories = taxonomy.categories_for(group)
        # A filing rule is global but categories belong to a group: a rule naming a category this
        # group doesn't have simply doesn't apply here, and the keyword rules get their turn.
        applicable_rules = [rule for rule in self._filing_rules if rule.get("category") in categories]
        by_filename = match_by_filename(document.file_name, applicable_rules)
        if by_filename.name is not None:
            return by_filename
        return match_category(document.content, categories, self._category_hints)
