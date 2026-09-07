"""Tests for the deterministic rules engine."""

from core.models.category import Taxonomy
from core.rules.rules_engine import RulesEngine


def test_rules_engine_resolves_group_and_category_by_exact_name() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements", "02 Architecture"]})
    engine = RulesEngine(category_hints={}, filing_rules=[])

    result = engine.classify(
        file_name="notes.txt",
        text="This is the Project Phoenix requirements document.",
        taxonomy=taxonomy,
    )

    assert result.group.name == "Project Phoenix"
    assert result.category.name == "01 Requirements"
    assert result.overall_confidence > 0.6


def test_rules_engine_returns_unresolved_for_unknown_content() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements"]})
    engine = RulesEngine(category_hints={}, filing_rules=[])

    result = engine.classify(file_name="mystery.txt", text="Nothing recognizable here.", taxonomy=taxonomy)

    assert result.group.name is None
    assert result.overall_confidence == 0.0
