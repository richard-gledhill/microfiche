"""Tests for holding a stage when the evidence for two folders is too close to call."""

from pathlib import Path
from typing import Any

import pytest
from microfiche.core.classifier import Classifier
from microfiche.core.config import ClassificationConfig, load_config
from microfiche.core.library.library_file import LibraryFile
from microfiche.core.models.category import Taxonomy
from microfiche.core.models.classification import CategoryMatch, GroupMatch
from microfiche.core.models.document import Document
from microfiche.core.models.unit import SortableUnit
from microfiche.core.rules.ambiguity import Candidate, choose
from microfiche.core.rules.group_rules import match_group
from microfiche.core.rules.keyword_rules import match_category
from microfiche.core.rules.rules_engine import RulesEngine

# region Test helpers


def _candidate(name: str, confidence: float, phrase: str | None = None) -> Candidate:
    return Candidate(name, confidence, f"reason {name}", phrase or name.lower())


def _settings(**overrides: Any) -> ClassificationConfig:
    return load_config(Path("does-not-exist")).classification.model_copy(update=overrides)


def _document(text: str, file_name: str = "notes.txt") -> Document:
    return Document(file_path=Path(file_name), file_name=file_name, extension=".txt", content=text)


def _library_file(hints: dict[str, list[str]], rules: list[str]) -> LibraryFile:
    children: list[dict[str, Any]] = [{"name": name, "hints": words} for name, words in hints.items()]
    children.append({"name": "Contracts", "rules": [{"pattern": pattern} for pattern in rules]})
    return LibraryFile.model_validate({"groups": [{"name": "*", "children": children}]})


# endregion

# region Choose


def test_choose_clear_leader_wins() -> None:
    choice = choose([_candidate("A", 1.0), _candidate("B", 0.75)], margin=0.1)

    assert choice.winner is not None
    assert choice.winner.name == "A"
    assert not choice.ambiguous


def test_choose_runner_up_within_margin_is_ambiguous_and_listed_strongest_first() -> None:
    choice = choose([_candidate("B", 0.95), _candidate("A", 1.0), _candidate("C", 0.5)], margin=0.1)

    assert choice.winner is None
    assert [c.name for c in choice.close] == ["A", "B"]
    assert choice.reason("groups") == "Several groups match about equally well: 'A' (1.00), 'B' (0.95)"


def test_choose_margin_boundary_inclusive() -> None:
    assert choose([_candidate("A", 0.9), _candidate("B", 0.75)], margin=0.15).ambiguous
    assert not choose([_candidate("A", 0.9), _candidate("B", 0.75)], margin=0.14).ambiguous


def test_choose_zero_margin_holds_only_exact_ties() -> None:
    assert choose([_candidate("A", 0.9), _candidate("B", 0.9)], margin=0).ambiguous
    assert not choose([_candidate("A", 0.9), _candidate("B", 0.89)], margin=0).ambiguous


def test_choose_order_does_not_matter() -> None:
    candidates = [_candidate("A", 1.0), _candidate("B", 1.0), _candidate("C", 0.4)]

    assert choose(candidates, 0.1) == choose(list(reversed(candidates)), 0.1)


def test_choose_name_inside_a_longer_matched_name_dropped() -> None:
    choice = choose([_candidate("Home", 1.0, "home"), _candidate("Home Insurance", 1.0, "home insurance")], margin=0.1)

    assert choice.winner is not None
    assert choice.winner.name == "Home Insurance"


def test_choose_nothing_is_not_ambiguous() -> None:
    choice = choose([], margin=0.1)

    assert choice.winner is None
    assert not choice.ambiguous


# endregion

# region Group stage


def test_match_group_two_exact_names_held_whatever_the_folder_order() -> None:
    text = "Phoenix depends on Atlas for storage."

    for names in (["Phoenix", "Atlas"], ["Atlas", "Phoenix"]):
        result = match_group(text, names, fuzzy_threshold=85, margin=0.1)

        assert result.name is None
        assert set(result.candidates) == {"Phoenix", "Atlas"}
        assert "'Atlas' (1.00)" in result.reason
        assert "'Phoenix' (1.00)" in result.reason


def test_match_group_exact_beats_sibling_that_only_looks_alike() -> None:
    result = match_group("Project X notes from the call.", ["Project X", "Project Y"], fuzzy_threshold=85, margin=0.1)

    assert result.name == "Project X"


def test_match_group_exact_with_a_fuzzy_rival_files_under_the_exact_one() -> None:
    result = match_group("Phoenix and the Atlantic office", ["Phoenix", "Atlas"], fuzzy_threshold=60, margin=0.1)

    assert result.name == "Phoenix"
    assert result.confidence == 1.0


def test_match_group_two_fuzzy_only_close_scores_held() -> None:
    result = match_group("the projct alpha file", ["Project Alpha", "Project Alpa"], fuzzy_threshold=85, margin=0.1)

    assert result.name is None
    assert len(result.candidates) == 2


def test_match_group_margin_defaults_to_zero_so_distinct_scores_still_choose() -> None:
    result = match_group("the projct alpha file", ["Project Alpha", "Project Alpine"], fuzzy_threshold=70)

    assert result.name == "Project Alpha"


# endregion

# region Category stage


def test_match_category_two_hints_held() -> None:
    result = match_category(
        "An invoice for the lecture",
        ["Bills", "Lectures"],
        {"Bills": ["invoice"], "Lectures": ["lecture"]},
        name_confidence=0.9,
        hint_confidence=0.75,
        margin=0.1,
    )

    assert result.name is None
    assert set(result.candidates) == {"Bills", "Lectures"}


def test_match_category_name_beats_another_categorys_hint_when_gap_wider_than_margin() -> None:
    args = ("The bills and a lecture", ["Bills", "Lectures"], {"Lectures": ["lecture"]})

    narrow = match_category(*args, name_confidence=0.9, hint_confidence=0.75, margin=0.1)
    wide = match_category(*args, name_confidence=0.9, hint_confidence=0.75, margin=0.15)

    assert narrow.name == "Bills"
    assert wide.name is None


def test_match_category_longer_name_wins_over_its_own_suffix() -> None:
    result = match_category(
        "Meeting notes from Monday",
        ["Notes", "Meeting Notes"],
        {},
        name_confidence=0.9,
        hint_confidence=0.75,
        margin=0.1,
    )

    assert result.name == "Meeting Notes"


def test_match_category_one_category_with_several_hints_not_ambiguous() -> None:
    result = match_category(
        "An invoice and a receipt",
        ["Bills"],
        {"Bills": ["invoice", "receipt"]},
        name_confidence=0.9,
        hint_confidence=0.75,
        margin=0.1,
    )

    assert result.name == "Bills"


# endregion

# region Rules engine and classifier


def test_rules_engine_filename_rule_decisive_over_text_ambiguity() -> None:
    taxonomy = Taxonomy(groups={"Acme": ["Contracts", "Bills", "Lectures"]})
    engine = RulesEngine(
        _library_file({"Bills": ["invoice"], "Lectures": ["lecture"]}, ["*contract*"]),
        _settings(ambiguity_margin=0.1),
    )

    result = engine.resolve_category(_document("An invoice for the lecture", "acme-contract.txt"), "Acme", taxonomy)

    assert result.name == "Contracts"


def test_rules_engine_flat_library_ambiguous_name_not_settled_by_hints() -> None:
    taxonomy = Taxonomy(groups={"Phoenix": [], "Atlas": []})
    engine = RulesEngine(
        LibraryFile.model_validate({"groups": [{"name": "Phoenix", "hints": ["storage"]}]}),
        _settings(ambiguity_margin=0.1),
    )

    result = engine.resolve_group(_document("Phoenix and Atlas share storage."), taxonomy)

    assert result.name is None
    assert set(result.candidates) == {"Phoenix", "Atlas"}


class _Scripted:
    name = "scripted"

    def __init__(self, answers: dict[str, tuple[GroupMatch, CategoryMatch]]) -> None:
        self._answers = answers

    def resolve_group(self, document: Document, taxonomy: Taxonomy) -> GroupMatch:
        return self._answers[document.file_name][0]

    def resolve_category(self, document: Document, group: str, taxonomy: Taxonomy) -> CategoryMatch:
        return self._answers[document.file_name][1]


def _known(group: str, category: str) -> tuple[GroupMatch, CategoryMatch]:
    return (
        GroupMatch(name=group, confidence=1.0, reason="g"),
        CategoryMatch(name=category, confidence=0.9, reason="c"),
    )


def test_classify_unit_ambiguous_document_casts_no_vote() -> None:
    taxonomy = Taxonomy(groups={"Phoenix": ["Reqs", "Arch"], "Atlas": ["Reqs"]})
    held = GroupMatch(name=None, confidence=0.0, reason="close", candidates=("Phoenix", "Atlas"))
    answers = {
        "a.md": _known("Phoenix", "Reqs"),
        "b.md": _known("Phoenix", "Reqs"),
        "c.md": (held, CategoryMatch(name=None, confidence=0.0, reason="Group unresolved")),
    }
    unit = SortableUnit(source_path=Path("folder"), kind="folder", documents=[_document("x", name) for name in answers])

    result = Classifier(_Scripted(answers)).classify_unit(unit, taxonomy)

    assert result.folders == ("Phoenix", "Reqs")


@pytest.mark.parametrize("stage", ["group", "category"])
def test_classification_result_ambiguous_reflects_either_stage(stage: str) -> None:
    taxonomy = Taxonomy(groups={"Phoenix": ["Reqs"]})
    if stage == "group":
        group = GroupMatch(name=None, confidence=0.0, reason="r", candidates=("A", "B"))
        category = CategoryMatch(name=None, confidence=0.0, reason="Group unresolved")
    else:
        group = GroupMatch(name="Phoenix", confidence=1.0, reason="r")
        category = CategoryMatch(name=None, confidence=0.0, reason="r", candidates=("Reqs", "Other"))
    answers = {"d.md": (group, category)}

    result = Classifier(_Scripted(answers)).classify_document(_document("x", "d.md"), taxonomy)

    assert result.ambiguous


# endregion
