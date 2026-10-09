"""Tests for the AI resolver, using a scripted provider instead of a real model."""

from pathlib import Path
from typing import Any

from core.ai.llm_classifier import LLMClassifier
from core.config import AIConfig, load_config
from core.models.category import Taxonomy
from core.models.document import Document

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
