"""Tests for the deterministic rules resolver, exercised through the Classifier that drives it."""

from pathlib import Path
from typing import Any

from core.classifier import Classifier
from core.config import ClassificationConfig, load_config
from core.models.category import Taxonomy
from core.models.document import Document
from core.rules.rules_engine import RulesEngine
from thefuzz import fuzz


def _settings(**overrides: Any) -> ClassificationConfig:
    """The packaged ``[classification]`` settings with ``overrides`` applied."""
    return load_config(Path("does-not-exist")).classification.model_copy(update=overrides)


def _document(text: str, file_name: str = "notes.txt") -> Document:
    return Document(file_path=Path(file_name), file_name=file_name, extension=Path(file_name).suffix, content=text)


def test_rules_engine_resolves_group_and_category_by_exact_name() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements", "02 Architecture"]})
    classifier = Classifier(RulesEngine(category_hints={}, filing_rules=[], settings=_settings()))

    result = classifier.classify_document(
        _document("This is the Project Phoenix requirements document."),
        taxonomy,
    )

    assert result.group.name == "Project Phoenix"
    assert result.category.name == "01 Requirements"
    assert result.overall_confidence > 0.6


def test_rules_engine_unknown_content_unresolved() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements"]})
    classifier = Classifier(RulesEngine(category_hints={}, filing_rules=[], settings=_settings()))

    result = classifier.classify_document(_document("Nothing recognizable here.", "mystery.txt"), taxonomy)

    assert result.group.name is None
    assert result.overall_confidence == 0.0


def test_filing_rule_category_missing_from_group_ignored() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements"], "Project Atlas": ["01 Requirements"]})
    rules = [{"pattern": "launch-plan*", "category": "04 Launch"}]
    engine = RulesEngine(category_hints={}, filing_rules=rules, settings=_settings())

    match = engine.resolve_category(_document("Project Atlas plan", "launch-plan.md"), "Project Atlas", taxonomy)

    assert match.name is None


def test_filing_rule_ignored_leaves_keyword_hints_to_decide() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements", "02 Architecture"]})
    rules = [{"pattern": "plan*", "category": "04 Launch"}]
    hints = {"02 Architecture": ["system diagram"]}
    engine = RulesEngine(category_hints=hints, filing_rules=rules, settings=_settings())

    match = engine.resolve_category(_document("See the system diagram.", "plan.md"), "Project Phoenix", taxonomy)

    assert match.name == "02 Architecture"


def test_filing_rule_existing_category_beats_keyword_hints() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements", "02 Architecture"]})
    rules = [{"pattern": "architecture*.pdf", "category": "02 Architecture"}]
    hints = {"01 Requirements": ["requirement"]}
    engine = RulesEngine(category_hints=hints, filing_rules=rules, settings=_settings())

    match = engine.resolve_category(
        _document("requirement list", "architecture-overview.pdf"), "Project Phoenix", taxonomy
    )

    assert match.name == "02 Architecture"
    assert match.confidence == 0.95


def test_rules_engine_name_match_scored_by_setting() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements"]})
    engine = RulesEngine(category_hints={}, filing_rules=[], settings=_settings(name_match_confidence=0.8))

    match = engine.resolve_category(_document("The requirements."), "Project Phoenix", taxonomy)

    assert (match.name, match.confidence) == ("01 Requirements", 0.8)


def test_rules_engine_hint_match_scored_by_setting() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["02 Architecture"]})
    hints = {"02 Architecture": ["system diagram"]}
    engine = RulesEngine(category_hints=hints, filing_rules=[], settings=_settings(hint_match_confidence=0.6))

    match = engine.resolve_category(_document("See the system diagram."), "Project Phoenix", taxonomy)

    assert (match.name, match.confidence) == ("02 Architecture", 0.6)


def test_rules_engine_filename_match_scored_by_setting() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["02 Architecture"]})
    rules = [{"pattern": "architecture*.pdf", "category": "02 Architecture"}]
    engine = RulesEngine(category_hints={}, filing_rules=rules, settings=_settings(filename_match_confidence=0.5))

    match = engine.resolve_category(_document("text", "architecture-overview.pdf"), "Project Phoenix", taxonomy)

    assert (match.name, match.confidence) == ("02 Architecture", 0.5)


def test_rules_engine_fuzzy_group_threshold_boundary_inclusive() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements"]})
    text = "Notes for Projct Phoeniix"  # a near miss, not the group's name
    score = fuzz.partial_ratio("project phoenix", text.lower())
    assert 0 < score < 100

    at_score = RulesEngine({}, [], _settings(fuzzy_group_threshold=score))
    above_score = RulesEngine({}, [], _settings(fuzzy_group_threshold=score + 1))

    assert at_score.resolve_group(_document(text), taxonomy).name == "Project Phoenix"
    assert above_score.resolve_group(_document(text), taxonomy).name is None


def test_classifier_from_config_uses_library_signal_strengths(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text(
        "[classification]\nhint_match_confidence = 0.6\n\n"
        '[category_hints.categories]\n"02 Architecture" = ["system diagram"]\n',
        encoding="utf-8",
    )
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements", "02 Architecture"]})

    result = Classifier.from_config(load_config(tmp_path)).classify_document(
        _document("Project Phoenix: see the system diagram."), taxonomy
    )

    assert result.category.name == "02 Architecture"
    assert result.category.confidence == 0.6
    assert result.confident is False  # 0.6 is under the default 0.75 threshold
