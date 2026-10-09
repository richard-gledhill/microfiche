"""Tests for the Classifier: stage-by-stage resolution, AI fallback, taxonomy checks, and folder votes."""

from pathlib import Path

import pytest
from core.classifier import Classifier
from core.models.category import Taxonomy
from core.models.classification import CategoryMatch, GroupMatch
from core.models.document import Document, UnreadableDocument
from core.models.unit import SortableUnit

PHOENIX = "Project Phoenix"
ATLAS = "Project Atlas"
REQS = "01 Requirements"
ARCH = "02 Architecture"

TAXONOMY = Taxonomy(groups={PHOENIX: [REQS, ARCH], ATLAS: [REQS, ARCH]})


# region Test helpers


def _document(text: str = "text", file_name: str = "doc.md") -> Document:
    return Document(file_path=Path(file_name), file_name=file_name, extension=".md", content=text)


def _group(name: str | None, confidence: float = 1.0) -> GroupMatch:
    return GroupMatch(name=name, confidence=confidence if name else 0.0, reason=f"group {name}")


def _category(name: str | None, confidence: float = 0.9) -> CategoryMatch:
    return CategoryMatch(name=name, confidence=confidence if name else 0.0, reason=f"category {name}")


class FakeResolver:
    """A scripted resolver that records what it was asked."""

    def __init__(self, name: str, group: GroupMatch, category: CategoryMatch) -> None:
        self.name = name
        self._group = group
        self._category = category
        self.group_calls = 0
        self.category_calls: list[str] = []

    def resolve_group(self, document: Document, taxonomy: Taxonomy) -> GroupMatch:
        self.group_calls += 1
        return self._group

    def resolve_category(self, document: Document, group: str, taxonomy: Taxonomy) -> CategoryMatch:
        self.category_calls.append(group)
        return self._category


class PerDocumentResolver:
    """Answers differently per document file name, for folder-vote tests."""

    name = "rules_engine"

    def __init__(self, answers: dict[str, tuple[GroupMatch, CategoryMatch]]) -> None:
        self._answers = answers

    def resolve_group(self, document: Document, taxonomy: Taxonomy) -> GroupMatch:
        return self._answers[document.file_name][0]

    def resolve_category(self, document: Document, group: str, taxonomy: Taxonomy) -> CategoryMatch:
        return self._answers[document.file_name][1]


# endregion


# region Public API


# region Happy path and threshold


def test_classify_document_confident_rules_answer_skips_fallback() -> None:
    rules = FakeResolver("rules_engine", _group(PHOENIX), _category(ARCH))
    fallback = FakeResolver("ai_fallback", _group(ATLAS, 0.7), _category(REQS, 0.7))

    result = Classifier(rules, fallback).classify_document(_document(), TAXONOMY)

    assert (result.group.name, result.category.name) == (PHOENIX, ARCH)
    assert result.classified_by == "rules_engine"
    assert result.confident is True
    assert fallback.group_calls == 0
    assert fallback.category_calls == []


def test_classify_document_confidence_takes_weaker_stage() -> None:
    rules = FakeResolver("rules_engine", _group(PHOENIX, 1.0), _category(ARCH, 0.9))

    result = Classifier(rules).classify_document(_document(), TAXONOMY)

    assert result.overall_confidence == 0.9


def test_classify_document_threshold_boundary_inclusive() -> None:
    rules = FakeResolver("rules_engine", _group(PHOENIX, 1.0), _category(ARCH, 0.8))

    assert Classifier(rules, threshold=0.8).classify_document(_document(), TAXONOMY).confident is True
    assert Classifier(rules, threshold=0.81).classify_document(_document(), TAXONOMY).confident is False


def test_classify_document_default_threshold_files_keyword_hint() -> None:
    rules = FakeResolver("rules_engine", _group(PHOENIX, 1.0), _category(ARCH, 0.75))  # a keyword-hint score

    assert Classifier(rules).classify_document(_document(), TAXONOMY).confident is True


def test_classify_document_stricter_threshold_reviews_hints() -> None:
    rules = FakeResolver("rules_engine", _group(PHOENIX, 1.0), _category(ARCH, 0.75))

    result = Classifier(rules, threshold=0.8).classify_document(_document(), TAXONOMY)

    assert result.confident is False
    assert result.category.name == ARCH  # still suggested, just not filed


def test_classify_document_no_category_never_confident() -> None:
    rules = FakeResolver("rules_engine", _group(PHOENIX), _category(None))

    assert Classifier(rules, threshold=0.0).classify_document(_document(), TAXONOMY).confident is False


def test_classifier_threshold_exposed() -> None:
    assert Classifier(FakeResolver("r", _group(None), _category(None)), threshold=0.5).threshold == 0.5


# endregion


# region Per-stage AI fallback


def test_classify_document_confident_group_ai_picks_category() -> None:
    rules = FakeResolver("rules_engine", _group(PHOENIX, 1.0), _category(None))
    fallback = FakeResolver("ai_fallback", _group(ATLAS, 0.7), _category(ARCH, 0.7))

    result = Classifier(rules, fallback, threshold=0.7).classify_document(_document(), TAXONOMY)

    assert (result.group.name, result.category.name) == (PHOENIX, ARCH)
    assert result.classified_by == "rules_engine+ai_fallback"
    assert fallback.group_calls == 0
    assert fallback.category_calls == [PHOENIX]


def test_classify_document_unresolved_rules_ai_decides_both() -> None:
    rules = FakeResolver("rules_engine", _group(None), _category(None))
    fallback = FakeResolver("ai_fallback", _group(ATLAS, 0.7), _category(REQS, 0.7))

    result = Classifier(rules, fallback, threshold=0.7).classify_document(_document(), TAXONOMY)

    assert (result.group.name, result.category.name) == (ATLAS, REQS)
    assert result.classified_by == "ai_fallback"
    assert result.confident is True


def test_classify_document_ai_none_keeps_weak_rules_suggestion() -> None:
    rules = FakeResolver("rules_engine", _group(PHOENIX, 0.85), _category(ARCH, 0.75))
    fallback = FakeResolver("ai_fallback", _group(None), _category(None))

    result = Classifier(rules, fallback, threshold=0.8).classify_document(_document(), TAXONOMY)  # 0.75 is weak at 0.8

    assert (result.group.name, result.category.name) == (PHOENIX, ARCH)
    assert result.classified_by == "rules_engine"
    assert result.confident is False


def test_classify_document_ai_replaces_weak_rules_answer() -> None:
    rules = FakeResolver("rules_engine", _group(PHOENIX, 0.85), _category(ARCH, 0.9))
    fallback = FakeResolver("ai_fallback", _group(ATLAS, 0.7), _category(ARCH, 0.7))

    result = Classifier(rules, fallback, threshold=0.9).classify_document(_document(), TAXONOMY)

    assert result.group.name == ATLAS
    assert result.group.confidence == 0.7


def test_classify_document_ai_below_threshold_used_not_confident() -> None:
    rules = FakeResolver("rules_engine", _group(None), _category(None))
    fallback = FakeResolver("ai_fallback", _group(PHOENIX, 0.7), _category(ARCH, 0.7))

    result = Classifier(rules, fallback).classify_document(_document(), TAXONOMY)  # default threshold 0.75

    assert (result.group.name, result.category.name) == (PHOENIX, ARCH)
    assert result.confident is False


def test_classify_document_no_fallback_weak_answer_stays_weak() -> None:
    rules = FakeResolver("rules_engine", _group(PHOENIX), _category(None))

    result = Classifier(rules).classify_document(_document(), TAXONOMY)

    assert result.group.name == PHOENIX
    assert result.category.name is None
    assert result.confident is False


def test_classify_document_no_group_skips_category_stage() -> None:
    rules = FakeResolver("rules_engine", _group(None), _category(ARCH))

    result = Classifier(rules).classify_document(_document(), TAXONOMY)

    assert result.category.name is None
    assert result.category.reason == "Group unresolved"
    assert rules.category_calls == []
    assert result.overall_confidence == 0.0


# endregion


# region Taxonomy enforced whoever answers


def test_classify_document_category_outside_group_rejected() -> None:
    rules = FakeResolver("rules_engine", _group(PHOENIX), _category("04 Launch", 0.95))

    result = Classifier(rules).classify_document(_document(), TAXONOMY)

    assert result.category.name is None
    assert "'04 Launch' is not an existing category of 'Project Phoenix'" in result.category.reason
    assert result.confident is False


def test_classify_document_group_outside_taxonomy_rejected() -> None:
    rules = FakeResolver("rules_engine", _group("Project Nowhere"), _category(ARCH))

    result = Classifier(rules).classify_document(_document(), TAXONOMY)

    assert result.group.name is None
    assert "'Project Nowhere' is not an existing group" in result.group.reason
    assert result.confident is False


def test_classify_document_rejected_category_lets_ai_try() -> None:
    rules = FakeResolver("rules_engine", _group(PHOENIX), _category("04 Launch", 0.95))
    fallback = FakeResolver("ai_fallback", _group(None), _category(ARCH, 0.7))

    result = Classifier(rules, fallback, threshold=0.7).classify_document(_document(), TAXONOMY)

    assert result.category.name == ARCH
    assert result.classified_by == "rules_engine+ai_fallback"


# endregion


# region Folder units


def _unit(names: list[str]) -> SortableUnit:
    documents = [_document(file_name=name) for name in names]
    return SortableUnit(source_path=Path("folder"), kind="folder", documents=documents)


def _voting_classifier(answers: dict[str, tuple[GroupMatch, CategoryMatch]]) -> Classifier:
    return Classifier(PerDocumentResolver(answers))


def test_classify_unit_single_document_classified_directly() -> None:
    rules = FakeResolver("rules_engine", _group(PHOENIX), _category(ARCH))
    unit = SortableUnit(source_path=Path("a.md"), kind="file", documents=[_document()])

    result = Classifier(rules).classify_unit(unit, TAXONOMY)

    assert (result.group.name, result.category.name) == (PHOENIX, ARCH)


def test_classify_unit_folder_filed_under_most_voted_pair() -> None:
    classifier = _voting_classifier({
        "a.md": (_group(PHOENIX), _category(ARCH)),
        "b.md": (_group(PHOENIX), _category(ARCH)),
        "c.md": (_group(ATLAS), _category(REQS)),
    })

    result = classifier.classify_unit(_unit(["a.md", "b.md", "c.md"]), TAXONOMY)

    assert (result.group.name, result.category.name) == (PHOENIX, ARCH)


def test_classify_unit_unique_plurality_wins() -> None:
    classifier = _voting_classifier({
        "a.md": (_group(PHOENIX), _category(ARCH)),
        "b.md": (_group(PHOENIX), _category(ARCH)),
        "c.md": (_group(PHOENIX), _category(REQS)),
        "d.md": (_group(ATLAS), _category(REQS)),
        "e.md": (_group(ATLAS), _category(ARCH)),
    })

    result = classifier.classify_unit(_unit(["a.md", "b.md", "c.md", "d.md", "e.md"]), TAXONOMY)

    assert (result.group.name, result.category.name) == (PHOENIX, ARCH)


def test_classify_unit_winner_shown_by_most_confident_document() -> None:
    classifier = _voting_classifier({
        "a.md": (_group(PHOENIX, 0.85), _category(ARCH, 0.75)),
        "b.md": (_group(PHOENIX, 1.0), _category(ARCH, 0.95)),
        "c.md": (_group(ATLAS), _category(REQS)),
    })

    result = classifier.classify_unit(_unit(["a.md", "b.md", "c.md"]), TAXONOMY)

    assert result.overall_confidence == 0.95


def test_classify_unit_tied_vote_goes_to_review() -> None:
    classifier = _voting_classifier({
        "a.md": (_group(PHOENIX), _category(ARCH)),
        "b.md": (_group(ATLAS), _category(REQS)),
    })

    result = classifier.classify_unit(_unit(["a.md", "b.md"]), TAXONOMY)

    assert result.group.name is None
    assert result.category.name is None
    assert result.confident is False
    assert result.overall_confidence == 0.0
    assert result.classified_by == "folder_vote"
    assert "Documents in this folder disagree" in result.category.reason
    assert "Project Phoenix/02 Architecture (1 documents)" in result.category.reason
    assert "Project Atlas/01 Requirements (1 documents)" in result.category.reason


def test_classify_unit_first_place_tie_with_trailing_pairs() -> None:
    classifier = _voting_classifier({
        "a.md": (_group(PHOENIX), _category(ARCH)),
        "b.md": (_group(PHOENIX), _category(ARCH)),
        "c.md": (_group(ATLAS), _category(REQS)),
        "d.md": (_group(ATLAS), _category(REQS)),
        "e.md": (_group(PHOENIX), _category(REQS)),
    })

    result = classifier.classify_unit(_unit(["a.md", "b.md", "c.md", "d.md", "e.md"]), TAXONOMY)

    assert result.confident is False
    assert result.classified_by == "folder_vote"
    assert "Project Phoenix/01 Requirements" not in result.category.reason


def test_classify_unit_documents_without_group_do_not_vote() -> None:
    classifier = _voting_classifier({
        "a.md": (_group(PHOENIX), _category(ARCH)),
        "b.md": (_group(None), _category(None)),
        "c.md": (_group(None), _category(None)),
    })

    result = classifier.classify_unit(_unit(["a.md", "b.md", "c.md"]), TAXONOMY)

    assert (result.group.name, result.category.name) == (PHOENIX, ARCH)


def test_classify_unit_no_group_resolved_shows_first_reason() -> None:
    classifier = _voting_classifier({
        "a.md": (GroupMatch(name=None, confidence=0.0, reason="first reason"), _category(None)),
        "b.md": (GroupMatch(name=None, confidence=0.0, reason="second reason"), _category(None)),
    })

    result = classifier.classify_unit(_unit(["a.md", "b.md"]), TAXONOMY)

    assert result.group.name is None
    assert result.group.reason == "first reason"


@pytest.mark.parametrize("threshold", [0.5, 0.8, 0.95])
def test_classify_unit_result_carries_threshold_decision(threshold: float) -> None:
    classifier = Classifier(
        PerDocumentResolver({
            "a.md": (_group(PHOENIX), _category(ARCH, 0.9)),
            "b.md": (_group(PHOENIX), _category(ARCH, 0.9)),
        }),
        threshold=threshold,
    )

    result = classifier.classify_unit(_unit(["a.md", "b.md"]), TAXONOMY)

    assert result.confident is (threshold <= 0.9)


# endregion


# region Units with nothing readable


def _unreadable(name: str, reason: str = "PackageNotFoundError: not a zip") -> UnreadableDocument:
    return UnreadableDocument(file_path=Path(name), reason=reason)


def test_classify_unit_unreadable_unit_unresolved_with_reason() -> None:
    rules = FakeResolver("rules_engine", _group(PHOENIX), _category(ARCH))
    unit = SortableUnit(
        source_path=Path("broken.docx"), kind="file", documents=[], unreadable=[_unreadable("broken.docx")]
    )

    result = Classifier(rules).classify_unit(unit, TAXONOMY)

    assert result.group.name is None
    assert result.category.name is None
    assert result.confident is False
    assert result.classified_by == "unreadable"
    assert result.category.reason == "Could not read 'broken.docx': PackageNotFoundError: not a zip"
    assert rules.group_calls == 0  # nothing to classify, so the resolvers are never asked


def test_classify_unit_names_every_unreadable_file() -> None:
    unit = SortableUnit(
        source_path=Path("bundle"),
        kind="folder",
        documents=[],
        unreadable=[_unreadable("a.docx", "reason a"), _unreadable("b.pdf", "reason b")],
    )

    result = Classifier(FakeResolver("rules_engine", _group(None), _category(None))).classify_unit(unit, TAXONOMY)

    assert "Could not read 'a.docx': reason a" in result.category.reason
    assert "Could not read 'b.pdf': reason b" in result.category.reason


def test_classify_unit_no_documents_says_so() -> None:
    unit = SortableUnit(source_path=Path("empty"), kind="folder", documents=[])

    result = Classifier(FakeResolver("rules_engine", _group(None), _category(None))).classify_unit(unit, TAXONOMY)

    assert result.category.reason == "No readable documents"
    assert result.confident is False


def test_classify_unit_unreadable_files_do_not_vote_or_block() -> None:
    unit = SortableUnit(
        source_path=Path("folder"),
        kind="folder",
        documents=[_document(file_name="a.md"), _document(file_name="b.md")],
        unreadable=[_unreadable("c.docx")],
    )
    classifier = _voting_classifier({
        "a.md": (_group(PHOENIX), _category(ARCH)),
        "b.md": (_group(PHOENIX), _category(ARCH)),
    })

    result = classifier.classify_unit(unit, TAXONOMY)

    assert (result.group.name, result.category.name) == (PHOENIX, ARCH)


# endregion


# endregion
