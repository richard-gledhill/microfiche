"""The AI resolver, used only when the rules can't confidently resolve a stage."""

from __future__ import annotations

import logging
import time

from core.ai.base import AIProvider
from core.ai.prompts import CATEGORY_RESOLUTION_PROMPT, GROUP_RESOLUTION_PROMPT
from core.config import AIConfig
from core.models.category import Taxonomy
from core.models.classification import CategoryMatch, GroupMatch
from core.models.document import Document
from core.utils.errors import describe_error

_logger = logging.getLogger(__name__)


class LLMClassifier:
    """Resolver backed by an ``AIProvider``.

    Asks the model to pick a group or category from the taxonomy, or to say none fit. It is a
    fallback resolver for ``core.classifier.Classifier``, which decides whether the answer is
    confident enough to use.

    If the provider fails - Ollama not running, a timeout, the optional package missing - the
    classifier stops asking for the rest of its life and answers "no match" from then on, so the
    run carries on with the rules alone and does not wait out a timeout for every document. The
    first failure is kept in ``failure`` for the caller to report once.

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
        self._failure: str | None = None

    @property
    def failure(self) -> str | None:
        """Why the provider stopped being asked (one line), or ``None`` if it has not failed."""

        return self._failure

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
        answer = self._ask(prompt)
        if answer is None:
            return GroupMatch(name=None, confidence=0.0, reason="AI fallback unavailable")
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
        answer = self._ask(prompt)
        if answer is None:
            return CategoryMatch(name=None, confidence=0.0, reason="AI fallback unavailable")
        if answer.upper() == "NONE" or answer not in categories:
            return CategoryMatch(name=None, confidence=0.0, reason="AI found no matching category")
        return CategoryMatch(name=answer, confidence=self._settings.ai_confidence, reason="Resolved by AI fallback")

    def _ask(self, prompt: str) -> str | None:
        """The provider's answer, or ``None`` if it has failed - now or on an earlier call.

        Any exception from the provider counts: the providers wrap third-party libraries that share no
        exception base, so a connection error, a timeout and a missing package all look different.
        """

        if self._failure is not None:
            return None
        started = time.perf_counter()
        try:
            answer = self._provider.complete(prompt).strip()
        except Exception as err:
            self._failure = describe_error(err)
            _logger.warning(
                "AI fallback unavailable (%s): the rest of the run uses the rules only, "
                "so anything only the AI could answer goes to review",
                self._failure,
            )
            return None
        # Only how long and how much: neither the prompt nor the answer, which can hold the document's text.
        _logger.debug("AI answered in %.2f s (%d prompt chars)", time.perf_counter() - started, len(prompt))
        return answer

    def _clip(self, text: str) -> str:
        """The part of ``text`` the AI is sent: all of it when ``max_document_chars`` is 0."""

        limit = self._settings.max_document_chars
        return text[:limit] if limit else text
