"""Tests for the AI resolver, using a scripted provider instead of a real model."""

from pathlib import Path

from core.ai.llm_classifier import LLMClassifier
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


def _document(text: str) -> Document:
    return Document(file_path=Path("doc.md"), file_name="doc.md", extension=".md", content=text)


def test_the_group_prompt_lists_the_groups_and_the_document() -> None:
    provider = ScriptedProvider("Acme Ltd")

    LLMClassifier(provider).resolve_group(_document("An agreement between parties."), TAXONOMY)

    (prompt,) = provider.prompts
    assert "Acme Ltd, Globex" in prompt
    assert "An agreement between parties." in prompt


def test_the_prompts_call_a_group_a_group_not_a_project() -> None:
    provider = ScriptedProvider("Acme Ltd")
    resolver = LLMClassifier(provider)

    resolver.resolve_group(_document("text"), TAXONOMY)
    resolver.resolve_category(_document("text"), "Acme Ltd", TAXONOMY)

    group_prompt, category_prompt = provider.prompts
    assert "existing groups" in group_prompt
    assert "project, client or course" in group_prompt
    assert 'the group "Acme Ltd"' in category_prompt
    assert "projects" not in group_prompt.lower().replace("project, client or course", "")


def test_the_category_prompt_lists_only_that_groups_categories() -> None:
    provider = ScriptedProvider("Invoices")

    LLMClassifier(provider).resolve_category(_document("Invoice 42"), "Acme Ltd", TAXONOMY)

    (prompt,) = provider.prompts
    assert "Contracts, Invoices" in prompt
    assert "Globex" not in prompt


def test_a_valid_group_answer_is_resolved_with_the_ai_confidence() -> None:
    match = LLMClassifier(ScriptedProvider("  Globex\n")).resolve_group(_document("text"), TAXONOMY)

    assert match.name == "Globex"
    assert match.confidence == 0.7


def test_none_and_unknown_answers_resolve_nothing() -> None:
    for answer in ("NONE", "none", "Initech"):
        resolver = LLMClassifier(ScriptedProvider(answer))

        assert resolver.resolve_group(_document("text"), TAXONOMY).name is None
        assert resolver.resolve_category(_document("text"), "Acme Ltd", TAXONOMY).name is None


def test_a_category_from_another_group_is_not_accepted() -> None:
    match = LLMClassifier(ScriptedProvider("Invoices")).resolve_category(_document("text"), "Globex", TAXONOMY)

    assert match.name is None


def test_long_documents_are_truncated_in_the_prompt() -> None:
    provider = ScriptedProvider("Acme Ltd")

    LLMClassifier(provider).resolve_group(_document("#" * 10_000), TAXONOMY)

    (prompt,) = provider.prompts
    assert prompt.count("#") == 4000


def test_the_resolver_identifies_itself_as_the_ai_fallback() -> None:
    assert LLMClassifier(ScriptedProvider("")).name == "ai_fallback"
