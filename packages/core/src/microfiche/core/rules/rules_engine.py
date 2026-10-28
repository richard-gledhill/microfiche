"""The deterministic resolver: filename, group and keyword rules, with no AI involved."""

from __future__ import annotations

from microfiche.core.config import ClassificationConfig
from microfiche.core.library.library_file import LibraryFile
from microfiche.core.models.category import Taxonomy
from microfiche.core.models.classification import CategoryMatch, GroupMatch
from microfiche.core.models.document import Document
from microfiche.core.rules.group_rules import match_group
from microfiche.core.rules.keyword_rules import match_category, match_group_hints
from microfiche.core.rules.metadata_rules import match_by_filename, match_group_by_filename


class RulesEngine:
    """Resolver backed by rules only.

    Proposes a group by name match, and a category by filename rule first, then category name
    or keyword hint - all scoped to the group's existing categories. The hints and rules come from
    the library file, so a group can have its own on top of the ones every group shares.

    It only proposes: ``microfiche.core.classifier.Classifier`` runs the two stages, decides what is
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

        In a flat library the group is also the destination, so a filename rule comes first and the groups'
        keyword hints last, as for a category in a two-level library.

        Args:
            document: The document to classify.
            taxonomy: The library's groups and categories.

        Returns:
            The proposed group, with ``name=None`` if none matched.
        """

        if not taxonomy.is_flat:
            return self._match_name(document, taxonomy)
        by_filename = match_group_by_filename(
            document.file_name,
            self._library_file.group_rules_for(taxonomy.group_names),
            confidence=self._settings.filename_match_confidence,
        )
        if by_filename.name is not None:
            return by_filename
        by_name = self._match_name(document, taxonomy)
        if by_name.name is not None or by_name.candidates:  # an ambiguous name is held, not settled by hints
            return by_name
        hints = {group: self._library_file.group_hints_for(group) for group in taxonomy.group_names}
        return match_group_hints(
            document.content,
            hints,
            confidence=self._settings.hint_match_confidence,
            normalise=self._settings.normalise_names,
        )

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
            normalise=self._settings.normalise_names,
            margin=self._settings.ambiguity_margin,
        )

    def _match_name(self, document: Document, taxonomy: Taxonomy) -> GroupMatch:
        return match_group(
            document.content,
            taxonomy.group_names,
            fuzzy_threshold=self._settings.fuzzy_group_threshold,
            normalise=self._settings.normalise_names,
            margin=self._settings.ambiguity_margin,
        )
