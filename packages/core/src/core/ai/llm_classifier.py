"""The AI resolver, used only when the rules can't confidently resolve a stage."""

from __future__ import annotations

from core.ai.base import AIProvider
from core.ai.prompts import CATEGORY_RESOLUTION_PROMPT, GROUP_RESOLUTION_PROMPT
from core.models.category import Taxonomy
from core.models.classification import CategoryMatch, GroupMatch
from core.models.document import Document

_MAX_DOCUMENT_CHARS = 4000
_AI_CONFIDENCE = 0.7


class LLMClassifier:
    """Resolver backed by an ``AIProvider``: asks the model to pick a group or category from the
    taxonomy, or to say none fit. It is a fallback resolver for ``core.classifier.Classifier``,
    which decides whether the answer is confident enough to use.
    """

    name: str = "ai_fallback"

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    def resolve_group(self, document: Document, taxonomy: Taxonomy) -> GroupMatch:
        prompt = GROUP_RESOLUTION_PROMPT.format(
            group_names=", ".join(taxonomy.group_names),
            document_text=document.content[:_MAX_DOCUMENT_CHARS],
        )
        answer = self._provider.complete(prompt).strip()
        if answer.upper() == "NONE" or answer not in taxonomy.group_names:
            return GroupMatch(name=None, confidence=0.0, reason="AI found no matching group")
        return GroupMatch(name=answer, confidence=_AI_CONFIDENCE, reason="Resolved by AI fallback")

    def resolve_category(self, document: Document, group: str, taxonomy: Taxonomy) -> CategoryMatch:
        categories = taxonomy.categories_for(group)
        prompt = CATEGORY_RESOLUTION_PROMPT.format(
            group_name=group,
            category_names=", ".join(categories),
            document_text=document.content[:_MAX_DOCUMENT_CHARS],
        )
        answer = self._provider.complete(prompt).strip()
        if answer.upper() == "NONE" or answer not in categories:
            return CategoryMatch(name=None, confidence=0.0, reason="AI found no matching category")
        return CategoryMatch(name=answer, confidence=_AI_CONFIDENCE, reason="Resolved by AI fallback")
