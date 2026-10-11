"""The deterministic resolver: filename, group and keyword rules, with no AI involved."""

from __future__ import annotations

from core.config import ClassificationConfig
from core.library.library_file import LibraryFile
from core.models.category import Taxonomy
from core.models.classification import CategoryMatch, GroupMatch
from core.models.document import Document
from core.rules.group_rules import match_group
from core.rules.keyword_rules import match_category
from core.rules.metadata_rules import match_by_filename


class RulesEngine:
    """Resolver backed by rules only.

    Proposes a group by name match, and a category by filename rule first, then category name
    or keyword hint - all scoped to the group's existing categories. The hints and rules come from
    the library file, so a group can have its own on top of the ones every group shares.

    It only proposes: ``core.classifier.Classifier`` runs the two stages, decides what is
    confident, and enforces the taxonomy.

    Args:
        library_file: The library's hints and filename rules.
        settings: The ``[classification]`` settings: how sure each kind of match is, and how close a
            near-miss to a group name must be.

    Attributes:
        name: Identifies the resolver in ``ClassificationResult.classified_by``.
    """

    name: str = "rules_engine"

    def __init__(self, library_file: LibraryFile, settings: ClassificationConfig) -> None:
        self._library_file = library_file
        self._settings = settings

    def resolve_group(self, document: Document, taxonomy: Taxonomy) -> GroupMatch:
        """Propose a group by matching the document's text against the taxonomy's group names.

        Args:
            document: The document to classify.
            taxonomy: The library's groups and categories.

        Returns:
            The proposed group, with ``name=None`` if none matched.
        """

        return match_group(document.content, taxonomy.group_names, fuzzy_threshold=self._settings.fuzzy_group_threshold)

    def resolve_category(self, document: Document, group: str, taxonomy: Taxonomy) -> CategoryMatch:
        """Propose a category of ``group``: by filename rule first, then by name or keyword hint.

        Args:
            document: The document to classify.
            group: The group the document was resolved to.
            taxonomy: The library's groups and categories.

        Returns:
            The proposed category, with ``name=None`` if none matched.
        """

        categories = taxonomy.categories_for(group)
        # The folders decide which categories exist: an entry for a category this group has no folder
        # for is never asked about, and the keyword rules get their turn.
        applicable_rules = self._library_file.rules_for(group, categories)
        by_filename = match_by_filename(
            document.file_name, applicable_rules, confidence=self._settings.filename_match_confidence
        )
        if by_filename.name is not None:
            return by_filename
        hints = {category: self._library_file.hints_for(group, category) for category in categories}
        return match_category(
            document.content,
            categories,
            hints,
            name_confidence=self._settings.name_match_confidence,
            hint_confidence=self._settings.hint_match_confidence,
        )
