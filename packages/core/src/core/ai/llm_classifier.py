"""The AI resolver, used only when the rules can't confidently resolve a stage."""

from __future__ import annotations

from core.ai.base import AIProvider
from core.ai.prompts import CATEGORY_RESOLUTION_PROMPT, GROUP_RESOLUTION_PROMPT
from core.config import AIConfig
from core.models.category import Taxonomy
from core.models.classification import CategoryMatch, GroupMatch
from core.models.document import Document


class LLMClassifier:
    """Resolver backed by an ``AIProvider``.

    Asks the model to pick a group or category from the taxonomy, or to say none fit. It is a
    fallback resolver for ``core.classifier.Classifier``, which decides whether the answer is
    confident enough to use.

    Args:
        provider: The model to ask.
        settings: The ``[ai]`` settings: how sure an AI answer is, and how much of a
            document is sent.

    Attributes:
        name: Identifies the resolver in ``ClassificationResult.classified_by``.
    """

    name: str = "ai_fallback"

    def __init__(self, provider: AIProvider, settings: AIConfig) -> None:
        self._provider = provider
        self._settings = settings

    def resolve_group(self, document: Document, taxonomy: Taxonomy) -> GroupMatch:
        """Ask the model which of the taxonomy's groups ``document`` belongs to.

        Args:
            document: The document to classify.
            taxonomy: The library's groups and categories.

        Returns:
            The group the model picked, or ``name=None`` if it said none fit or named something
            that isn't an existing group.
        """

        prompt = GROUP_RESOLUTION_PROMPT.format(
            group_names=", ".join(taxonomy.group_names),
            document_text=self._clip(document.content),
        )
        answer = self._provider.complete(prompt).strip()
        if answer.upper() == "NONE" or answer not in taxonomy.group_names:
            return GroupMatch(name=None, confidence=0.0, reason="AI found no matching group")
        return GroupMatch(name=answer, confidence=self._settings.ai_confidence, reason="Resolved by AI fallback")

    def resolve_category(self, document: Document, group: str, taxonomy: Taxonomy) -> CategoryMatch:
        """Ask the model which of ``group``'s categories ``document`` belongs to.

        Args:
            document: The document to classify.
            group: The group the document was resolved to.
            taxonomy: The library's groups and categories.

        Returns:
            The category the model picked, or ``name=None`` if it said none fit or named
            something that isn't an existing category of ``group``.
        """

        categories = taxonomy.categories_for(group)
        prompt = CATEGORY_RESOLUTION_PROMPT.format(
            group_name=group,
            category_names=", ".join(categories),
            document_text=self._clip(document.content),
        )
        answer = self._provider.complete(prompt).strip()
        if answer.upper() == "NONE" or answer not in categories:
            return CategoryMatch(name=None, confidence=0.0, reason="AI found no matching category")
        return CategoryMatch(name=answer, confidence=self._settings.ai_confidence, reason="Resolved by AI fallback")

    def _clip(self, text: str) -> str:
        """The part of ``text`` the AI is sent: all of it when ``max_document_chars`` is 0."""

        limit = self._settings.max_document_chars
        return text[:limit] if limit else text
