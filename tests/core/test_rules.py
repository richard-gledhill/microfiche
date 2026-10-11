"""Tests for the deterministic rules resolver, exercised through the Classifier that drives it."""

from pathlib import Path
from typing import Any

from core.classifier import Classifier
from core.config import ClassificationConfig, load_config
from core.library.library import Library
from core.library.library_file import LibraryFile
from core.models.category import Taxonomy
from core.models.document import Document
from core.rules.rules_engine import RulesEngine
from rapidfuzz import fuzz


def _settings(**overrides: Any) -> ClassificationConfig:
    """The packaged ``[classification]`` settings with ``overrides`` applied."""
    return load_config(Path("does-not-exist")).classification.model_copy(update=overrides)


def _library_file(hints: dict[str, list[str]] | None = None, rules: list[dict[str, str]] | None = None) -> LibraryFile:
    """A library file that applies ``hints`` and ``rules`` (the old shapes) to every group, through a ``*`` entry."""

    hints = hints or {}
    rules = rules or []
    names = list(dict.fromkeys([*hints, *(rule["category"] for rule in rules)]))
    children = [
        {
            "name": name,
            "hints": hints.get(name, []),
            "rules": [{"pattern": rule["pattern"]} for rule in rules if rule["category"] == name],
        }
        for name in names
    ]
    return LibraryFile.model_validate({"groups": [{"name": "*", "children": children}]})


def _document(text: str, file_name: str = "notes.txt") -> Document:
    return Document(file_path=Path(file_name), file_name=file_name, extension=Path(file_name).suffix, content=text)


def test_rules_engine_resolves_group_and_category_by_exact_name() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements", "02 Architecture"]})
    classifier = Classifier(RulesEngine(_library_file(), _settings()))

    result = classifier.classify_document(
        _document("This is the Project Phoenix requirements document."),
        taxonomy,
    )

    assert result.group.name == "Project Phoenix"
    assert result.category.name == "01 Requirements"
    assert result.overall_confidence > 0.6


def test_rules_engine_unknown_content_unresolved() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements"]})
    classifier = Classifier(RulesEngine(_library_file(), _settings()))

    result = classifier.classify_document(_document("Nothing recognizable here.", "mystery.txt"), taxonomy)

    assert result.group.name is None
    assert result.overall_confidence == 0.0


def test_filing_rule_category_missing_from_group_ignored() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements"], "Project Atlas": ["01 Requirements"]})
    rules = [{"pattern": "launch-plan*", "category": "04 Launch"}]
    engine = RulesEngine(_library_file(rules=rules), _settings())

    match = engine.resolve_category(_document("Project Atlas plan", "launch-plan.md"), "Project Atlas", taxonomy)

    assert match.name is None


def test_filing_rule_ignored_leaves_keyword_hints_to_decide() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements", "02 Architecture"]})
    rules = [{"pattern": "plan*", "category": "04 Launch"}]
    hints = {"02 Architecture": ["system diagram"]}
    engine = RulesEngine(_library_file(hints=hints, rules=rules), _settings())

    match = engine.resolve_category(_document("See the system diagram.", "plan.md"), "Project Phoenix", taxonomy)

    assert match.name == "02 Architecture"


def test_filing_rule_existing_category_beats_keyword_hints() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements", "02 Architecture"]})
    rules = [{"pattern": "architecture*.pdf", "category": "02 Architecture"}]
    hints = {"01 Requirements": ["requirement"]}
    engine = RulesEngine(_library_file(hints=hints, rules=rules), _settings())

    match = engine.resolve_category(
        _document("requirement list", "architecture-overview.pdf"), "Project Phoenix", taxonomy
    )

    assert match.name == "02 Architecture"
    assert match.confidence == 0.95


def test_rules_engine_name_match_scored_by_setting() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements"]})
    engine = RulesEngine(_library_file(), _settings(name_match_confidence=0.8))

    match = engine.resolve_category(_document("The requirements."), "Project Phoenix", taxonomy)

    assert (match.name, match.confidence) == ("01 Requirements", 0.8)


def test_rules_engine_hint_match_scored_by_setting() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["02 Architecture"]})
    hints = {"02 Architecture": ["system diagram"]}
    engine = RulesEngine(_library_file(hints=hints), _settings(hint_match_confidence=0.6))

    match = engine.resolve_category(_document("See the system diagram."), "Project Phoenix", taxonomy)

    assert (match.name, match.confidence) == ("02 Architecture", 0.6)


def test_rules_engine_filename_match_scored_by_setting() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["02 Architecture"]})
    rules = [{"pattern": "architecture*.pdf", "category": "02 Architecture"}]
    engine = RulesEngine(_library_file(rules=rules), _settings(filename_match_confidence=0.5))

    match = engine.resolve_category(_document("text", "architecture-overview.pdf"), "Project Phoenix", taxonomy)

    assert (match.name, match.confidence) == ("02 Architecture", 0.5)


def test_rules_engine_fuzzy_group_threshold_boundary_inclusive() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements"]})
    text = "Notes for Projct Phoeniix"  # a near miss, not the group's name
    score = round(fuzz.partial_ratio("project phoenix", text.lower()))
    assert 0 < score < 100

    at_score = RulesEngine(_library_file(), _settings(fuzzy_group_threshold=score))
    above_score = RulesEngine(_library_file(), _settings(fuzzy_group_threshold=score + 1))

    assert at_score.resolve_group(_document(text), taxonomy).name == "Project Phoenix"
    assert above_score.resolve_group(_document(text), taxonomy).name is None


def test_classifier_from_library_uses_library_signal_strengths_and_library_file(tmp_path: Path) -> None:
    (tmp_path / ".microfiche").mkdir()
    (tmp_path / ".microfiche" / "microfiche-config.toml").write_text(
        "[classification]\nhint_match_confidence = 0.6\n", encoding="utf-8"
    )
    (tmp_path / ".microfiche" / "microfiche-library.json").write_text(
        '{"groups": [{"name": "*", "children": [{"name": "02 Architecture", "hints": ["system diagram"]}]}]}',
        encoding="utf-8",
    )
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements", "02 Architecture"]})

    result = Classifier.from_library(Library(tmp_path)).classify_document(
        _document("Project Phoenix: see the system diagram."), taxonomy
    )

    assert result.category.name == "02 Architecture"
    assert result.category.confidence == 0.6
    assert result.confident is False  # 0.6 is under the default 0.75 threshold


def test_rules_engine_group_entry_hints_apply_to_that_group_only() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["02 Architecture"], "Project Atlas": ["02 Architecture"]})
    library_file = LibraryFile.model_validate({
        "groups": [
            {"name": "Project Phoenix", "children": [{"name": "02 Architecture", "hints": ["adr"]}]},
        ]
    })
    engine = RulesEngine(library_file, _settings())

    phoenix = engine.resolve_category(_document("See the ADR."), "Project Phoenix", taxonomy)
    atlas = engine.resolve_category(_document("See the ADR."), "Project Atlas", taxonomy)

    assert phoenix.name == "02 Architecture"
    assert atlas.name is None


def test_rules_engine_group_entry_adds_to_shared_hints() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["02 Architecture"]})
    library_file = LibraryFile.model_validate({
        "groups": [
            {"name": "*", "children": [{"name": "02 Architecture", "hints": ["system diagram"]}]},
            {"name": "Project Phoenix", "children": [{"name": "02 Architecture", "hints": ["adr"]}]},
        ]
    })
    engine = RulesEngine(library_file, _settings())

    shared = engine.resolve_category(_document("See the system diagram."), "Project Phoenix", taxonomy)
    own = engine.resolve_category(_document("See the ADR."), "Project Phoenix", taxonomy)

    assert shared.name == own.name == "02 Architecture"


def test_rules_engine_group_entry_filing_rule_applies_to_that_group_only() -> None:
    taxonomy = Taxonomy(groups={"Project Phoenix": ["02 Architecture"], "Project Atlas": ["02 Architecture"]})
    library_file = LibraryFile.model_validate({
        "groups": [
            {
                "name": "Project Phoenix",
                "children": [{"name": "02 Architecture", "rules": [{"pattern": "adr-*"}]}],
            }
        ]
    })
    engine = RulesEngine(library_file, _settings())

    phoenix = engine.resolve_category(_document("text", "adr-001.md"), "Project Phoenix", taxonomy)
    atlas = engine.resolve_category(_document("text", "adr-001.md"), "Project Atlas", taxonomy)

    assert phoenix.name == "02 Architecture"
    assert atlas.name is None


def test_rules_engine_entry_for_missing_folder_never_proposed() -> None:
    # The folders decide what exists: a rule for a category this group has no folder for is ignored.
    taxonomy = Taxonomy(groups={"Project Phoenix": ["01 Requirements"]})
    library_file = _library_file(rules=[{"pattern": "launch-plan*", "category": "04 Launch"}])
    engine = RulesEngine(library_file, _settings())

    match = engine.resolve_category(_document("text", "launch-plan.md"), "Project Phoenix", taxonomy)

    assert match.name is None


def test_rules_engine_fuzzy_group_score_rounded_before_threshold() -> None:
    # The raw score is 84.6; it is rounded to 85 before it is compared with the threshold, so it is accepted.
    name = "zedlxgoutuhhg"
    text = "notes about zedoxgoutuhig for the team"
    assert 84.5 < fuzz.partial_ratio(name, text) < 85
    taxonomy = Taxonomy(groups={name: ["01 Requirements"]})
    engine = RulesEngine(_library_file(), _settings(fuzzy_group_threshold=85))

    match = engine.resolve_group(_document(text), taxonomy)

    assert (match.name, match.confidence) == (name, 0.85)
