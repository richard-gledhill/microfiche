"""Tests for the AI resolver, using a scripted provider instead of a real model."""

import logging
import re
from pathlib import Path
from typing import Any

import pytest
from microfiche.core.ai.llm_classifier import LLMClassifier
from microfiche.core.config import AIConfig, load_config
from microfiche.core.models.category import Taxonomy
from microfiche.core.models.document import Document

TAXONOMY = Taxonomy(groups={"Acme Ltd": ["Contracts", "Invoices"], "Globex": ["Contracts"]})


class ScriptedProvider:
    """Returns a fixed answer and remembers the prompts it was sent."""

    def __init__(self, answer: str) -> None:
        self._answer = answer
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._answer


def _settings(**overrides: Any) -> AIConfig:
    """The packaged ``[ai]`` settings with ``overrides`` applied."""
    return load_config(Path("does-not-exist")).ai.model_copy(update=overrides)


def _document(text: str) -> Document:
    return Document(file_path=Path("doc.md"), file_name="doc.md", extension=".md", content=text)


def test_llm_classifier_group_prompt_lists_groups_and_document() -> None:
    provider = ScriptedProvider("Acme Ltd")

    LLMClassifier(provider, _settings()).resolve_group(_document("An agreement between parties."), TAXONOMY)

    (prompt,) = provider.prompts
    assert "Acme Ltd, Globex" in prompt
    assert "An agreement between parties." in prompt


def test_llm_classifier_prompts_say_group_not_project() -> None:
    provider = ScriptedProvider("Acme Ltd")
    resolver = LLMClassifier(provider, _settings())

    resolver.resolve_group(_document("text"), TAXONOMY)
    resolver.resolve_category(_document("text"), "Acme Ltd", TAXONOMY)

    group_prompt, category_prompt = provider.prompts
    assert "existing groups" in group_prompt
    assert "project, client or course" in group_prompt
    assert 'the group "Acme Ltd"' in category_prompt
    assert "projects" not in group_prompt.lower().replace("project, client or course", "")


def test_llm_classifier_category_prompt_only_group_categories() -> None:
    provider = ScriptedProvider("Invoices")

    LLMClassifier(provider, _settings()).resolve_category(_document("Invoice 42"), "Acme Ltd", TAXONOMY)

    (prompt,) = provider.prompts
    assert "Contracts, Invoices" in prompt
    assert "Globex" not in prompt


def test_llm_classifier_category_group_without_categories_skips_provider() -> None:
    provider = ScriptedProvider("Contracts")
    taxonomy = Taxonomy(groups={"Acme Ltd": []})

    match = LLMClassifier(provider, _settings()).resolve_category(_document("text"), "Acme Ltd", taxonomy)

    assert provider.prompts == []
    assert match.name is None
    assert match.confidence == 0.0
    assert match.reason == "Group has no categories"


def test_llm_classifier_valid_group_answer_uses_ai_confidence() -> None:
    match = LLMClassifier(ScriptedProvider("  Globex\n"), _settings()).resolve_group(_document("text"), TAXONOMY)

    assert match.name == "Globex"
    assert match.confidence == 0.7


def test_llm_classifier_none_and_unknown_answers_resolve_nothing() -> None:
    for answer in ("NONE", "none", "Initech"):
        resolver = LLMClassifier(ScriptedProvider(answer), _settings())

        assert resolver.resolve_group(_document("text"), TAXONOMY).name is None
        assert resolver.resolve_category(_document("text"), "Acme Ltd", TAXONOMY).name is None


def test_llm_classifier_category_from_other_group_rejected() -> None:
    match = LLMClassifier(ScriptedProvider("Invoices"), _settings()).resolve_category(
        _document("text"), "Globex", TAXONOMY
    )

    assert match.name is None


def test_llm_classifier_prompt_truncates_long_documents() -> None:
    provider = ScriptedProvider("Acme Ltd")

    LLMClassifier(provider, _settings()).resolve_group(_document("#" * 10_000), TAXONOMY)

    (prompt,) = provider.prompts
    assert prompt.count("#") == 4000


def test_llm_classifier_name_ai_fallback() -> None:
    assert LLMClassifier(ScriptedProvider(""), _settings()).name == "ai_fallback"


def test_llm_classifier_answer_scored_by_ai_confidence_setting() -> None:
    group_resolver = LLMClassifier(ScriptedProvider("Acme Ltd"), _settings(ai_confidence=0.5))
    category_resolver = LLMClassifier(ScriptedProvider("Invoices"), _settings(ai_confidence=0.5))

    assert group_resolver.resolve_group(_document("text"), TAXONOMY).confidence == 0.5
    assert category_resolver.resolve_category(_document("text"), "Acme Ltd", TAXONOMY).confidence == 0.5


def test_llm_classifier_sends_only_max_document_chars_setting() -> None:
    provider = ScriptedProvider("Acme Ltd")
    resolver = LLMClassifier(provider, _settings(max_document_chars=10))

    resolver.resolve_group(_document("0123456789ABCDEF"), TAXONOMY)
    resolver.resolve_category(_document("0123456789ABCDEF"), "Acme Ltd", TAXONOMY)

    for prompt in provider.prompts:
        assert "0123456789" in prompt
        assert "ABCDEF" not in prompt


def test_llm_classifier_zero_max_document_chars_sends_whole_document() -> None:
    # Slicing with [:0] would send nothing at all, so 0 has to be handled as "no limit".
    provider = ScriptedProvider("Acme Ltd")
    resolver = LLMClassifier(provider, _settings(max_document_chars=0))
    text = "x" * 10_000 + "END"

    resolver.resolve_group(_document(text), TAXONOMY)
    resolver.resolve_category(_document(text), "Acme Ltd", TAXONOMY)

    for prompt in provider.prompts:
        assert text in prompt


# region A provider that fails


class FailingProvider:
    """Raises on every call, and counts the calls."""

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        raise self._error


def test_llm_classifier_failure_none_until_provider_fails() -> None:
    classifier = LLMClassifier(ScriptedProvider("Acme Ltd"), _settings())

    classifier.resolve_group(_document("text"), TAXONOMY)

    assert classifier.failure is None


def test_llm_classifier_provider_failure_resolves_nothing_and_is_kept() -> None:
    provider = FailingProvider(ConnectionError("connection refused"))
    classifier = LLMClassifier(provider, _settings())

    match = classifier.resolve_group(_document("text"), TAXONOMY)

    assert (match.name, match.confidence, match.reason) == (None, 0.0, "AI fallback unavailable")
    assert classifier.failure == "ConnectionError: connection refused"


def test_llm_classifier_provider_asked_only_once_after_failure() -> None:
    provider = FailingProvider(TimeoutError("timed out"))
    classifier = LLMClassifier(provider, _settings())

    classifier.resolve_group(_document("one"), TAXONOMY)
    classifier.resolve_category(_document("two"), "Acme Ltd", TAXONOMY)
    classifier.resolve_group(_document("three"), TAXONOMY)

    assert provider.calls == 1  # a dead provider is not waited on again for every document
    assert classifier.failure == "TimeoutError: timed out"


def test_llm_classifier_category_stage_failure_resolves_nothing() -> None:
    classifier = LLMClassifier(FailingProvider(ConnectionError("down")), _settings())

    match = classifier.resolve_category(_document("text"), "Acme Ltd", TAXONOMY)

    assert (match.name, match.confidence) == (None, 0.0)


def test_llm_classifier_missing_optional_package_counts_as_unavailable() -> None:
    provider = FailingProvider(ModuleNotFoundError("No module named 'ollama'"))
    classifier = LLMClassifier(provider, _settings())

    classifier.resolve_group(_document("text"), TAXONOMY)

    assert classifier.failure == "ModuleNotFoundError: No module named 'ollama'"


# endregion


def test_llm_classifier_logs_call_timing_not_prompt_or_answer(caplog: pytest.LogCaptureFixture) -> None:
    marker = "UNIQUE-DOCUMENT-TEXT-MARKER"
    caplog.set_level(logging.DEBUG, logger="microfiche.core")

    LLMClassifier(ScriptedProvider("Acme Ltd"), _settings()).resolve_group(_document(marker), TAXONOMY)

    [record] = [r for r in caplog.records if r.name == "microfiche.core.ai.llm_classifier"]
    assert record.levelno == logging.DEBUG
    assert re.fullmatch(r"AI answered in \d+\.\d{2} s \(\d+ prompt chars\)", record.getMessage())
    assert marker not in caplog.text  # the document's text is sent to the model, never to the log
    assert "Acme Ltd" not in caplog.text  # nor is the model's answer


def test_llm_classifier_failure_logged_once_as_warning(caplog: pytest.LogCaptureFixture) -> None:
    class DownProvider:
        _error = ConnectionError("connection refused")

        def complete(self, prompt: str) -> str:
            raise self._error

    caplog.set_level(logging.DEBUG, logger="microfiche.core")
    resolver = LLMClassifier(DownProvider(), _settings())

    resolver.resolve_group(_document("first"), TAXONOMY)
    resolver.resolve_group(_document("second"), TAXONOMY)  # not asked again, so no second warning

    warnings = [
        r for r in caplog.records if r.name == "microfiche.core.ai.llm_classifier" and r.levelno == logging.WARNING
    ]
    (warning,) = warnings
    assert "ConnectionError: connection refused" in warning.getMessage()
    assert "rules only" in warning.getMessage()
