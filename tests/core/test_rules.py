"""Tests for the deterministic rules resolver, exercised through the Classifier that drives it."""

from pathlib import Path

from core.classifier import Classifier
from core.models.category import Taxonomy
from core.models.document import Document
from core.rules.rules_engine import RulesEngine


def _document(text: str, file_name: str = "notes.txt") -> Document:
    return Document(file_path=Path(file_name), file_name=file_name, extension=Path(file_name).suffix, content=text)


def test_rules_engine_resolves_group_and_category_by_exact_name() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements", "02 Architecture"]})
    classifier = Classifier(RulesEngine(category_hints={}, filing_rules=[]))

    result = classifier.classify_document(
        _document("This is the Project Phoenix requirements document."),
        taxonomy,
    )

    assert result.group.name == "Project Phoenix"
    assert result.category.name == "01 Requirements"
    assert result.overall_confidence > 0.6


def test_rules_engine_returns_unresolved_for_unknown_content() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements"]})
    classifier = Classifier(RulesEngine(category_hints={}, filing_rules=[]))

    result = classifier.classify_document(_document("Nothing recognizable here.", "mystery.txt"), taxonomy)

    assert result.group.name is None
    assert result.overall_confidence == 0.0


def test_a_filing_rule_naming_a_category_the_group_lacks_does_not_apply() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements"], "Project Atlas": ["01 Requirements"]})
    rules = [{"pattern": "launch-plan*", "category": "04 Launch"}]
    engine = RulesEngine(category_hints={}, filing_rules=rules)

    match = engine.resolve_category(_document("Project Atlas plan", "launch-plan.md"), "Project Atlas", taxonomy)

    assert match.name is None


def test_a_filing_rule_that_does_not_apply_leaves_keyword_hints_to_decide() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements", "02 Architecture"]})
    rules = [{"pattern": "plan*", "category": "04 Launch"}]
    hints = {"02 Architecture": ["system diagram"]}
    engine = RulesEngine(category_hints=hints, filing_rules=rules)

    match = engine.resolve_category(_document("See the system diagram.", "plan.md"), "Project Phoenix", taxonomy)

    assert match.name == "02 Architecture"


def test_a_filing_rule_naming_an_existing_category_wins_over_keyword_hints() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements", "02 Architecture"]})
    rules = [{"pattern": "architecture*.pdf", "category": "02 Architecture"}]
    hints = {"01 Requirements": ["requirement"]}
    engine = RulesEngine(category_hints=hints, filing_rules=rules)

    match = engine.resolve_category(
        _document("requirement list", "architecture-overview.pdf"), "Project Phoenix", taxonomy
    )

    assert match.name == "02 Architecture"
    assert match.confidence == 0.95
