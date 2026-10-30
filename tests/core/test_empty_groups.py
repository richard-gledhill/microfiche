"""Tests for filing straight into a group that has no category folders (``[sorting] file_in_empty_groups``)."""

from pathlib import Path

import pytest
from microfiche.core.classifier import Classifier
from microfiche.core.library.library import Library
from microfiche.core.models.category import Taxonomy
from microfiche.core.models.classification import CategoryMatch, GroupMatch
from microfiche.core.models.document import Document
from microfiche.core.organizer import run_sort
from microfiche.core.reclassify import run_reclassify
from microfiche.core.review import ReviewSession

# region Test helpers


_FINANCE_NOTE = "Finance budget for the year, as agreed with Finance."
_PHOENIX_NOTE = "Project Phoenix requirements for the launch."


def _library(tmp_path: Path, *, on: bool) -> Path:
    """A depth-2 library: ``Finance`` has no category folders, ``Project Phoenix`` has one."""

    root = tmp_path / "library"
    (root / "Finance").mkdir(parents=True)
    (root / "Project Phoenix" / "Requirements").mkdir(parents=True)
    (root / "_sorting").mkdir()
    (root / ".microfiche").mkdir()
    (root / ".microfiche" / "microfiche-config.toml").write_text(
        f"[sorting]\nfile_in_empty_groups = {str(on).lower()}\n", encoding="utf-8"
    )
    return root


def _document(text: str) -> Document:
    return Document(file_path=Path("doc.md"), file_name="doc.md", extension=".md", content=text)


class _Resolver:
    """Names ``Finance`` and records every category question."""

    name = "scripted"

    def __init__(self) -> None:
        self.category_calls: list[str] = []

    def resolve_group(self, document: Document, taxonomy: Taxonomy) -> GroupMatch:
        return GroupMatch(name="Finance", confidence=1.0, reason="named")

    def resolve_category(self, document: Document, group: str, taxonomy: Taxonomy) -> CategoryMatch:
        self.category_calls.append(group)
        return CategoryMatch(name=None, confidence=0.0, reason="none")


# endregion

# region Taxonomy


def test_taxonomy_is_leaf_group_without_categories() -> None:
    taxonomy = Taxonomy(groups={"Finance": [], "Phoenix": ["Reqs"]}, depth=2)

    assert taxonomy.is_leaf("Finance")
    assert not taxonomy.is_leaf("Phoenix")
    assert not taxonomy.is_leaf("Unknown")


def test_taxonomy_is_leaf_flat_library_never() -> None:
    assert not Taxonomy(groups={"Finance": []}, depth=1).is_leaf("Finance")


# endregion

# region Classifier


def test_classify_document_leaf_group_filed_in_group_and_category_not_asked() -> None:
    rules = _Resolver()
    classifier = Classifier(rules, file_in_empty_groups=True)

    result = classifier.classify_document(_document("x"), Taxonomy(groups={"Finance": []}))

    assert result.confident
    assert result.folders == ("Finance",)
    assert rules.category_calls == []


def test_classify_document_leaf_group_off_goes_to_review() -> None:
    rules = _Resolver()

    result = Classifier(rules).classify_document(_document("x"), Taxonomy(groups={"Finance": []}))

    assert not result.confident
    assert rules.category_calls == ["Finance"]


def test_classify_document_group_with_categories_still_needs_a_category() -> None:
    rules = _Resolver()

    result = Classifier(rules, file_in_empty_groups=True).classify_document(
        _document("x"), Taxonomy(groups={"Finance": ["Budgets"]})
    )

    assert not result.confident
    assert rules.category_calls == ["Finance"]


# endregion

# region Sort


def test_run_sort_on_files_unit_straight_into_empty_group(tmp_path: Path) -> None:
    root = _library(tmp_path, on=True)
    (root / "_sorting" / "budget.md").write_text(_FINANCE_NOTE, encoding="utf-8")
    (root / "_sorting" / "plan.md").write_text(_PHOENIX_NOTE, encoding="utf-8")

    report = run_sort(Library(root))

    assert (root / "Finance" / "budget.md").is_file()
    assert (root / "Project Phoenix" / "Requirements" / "plan.md").is_file()
    assert not report.needs_review
    assert report.into_empty_groups == 1


def test_run_sort_off_leaves_empty_group_unit_for_review(tmp_path: Path) -> None:
    root = _library(tmp_path, on=False)
    (root / "_sorting" / "budget.md").write_text(_FINANCE_NOTE, encoding="utf-8")

    report = run_sort(Library(root))

    assert (root / "_sorting" / "budget.md").is_file()
    assert [unit.source_path.name for unit, _ in report.needs_review] == ["budget.md"]
    assert report.into_empty_groups == 0


# endregion

# region Review


def _review(root: Path) -> ReviewSession:
    return ReviewSession.start(Library(root))


def test_review_can_file_in_group_only_when_on_and_group_has_no_categories(tmp_path: Path) -> None:
    on = _review(_library(tmp_path / "on", on=True))
    off = _review(_library(tmp_path / "off", on=False))

    assert on.can_file_in_group("Finance")
    assert not on.can_file_in_group("Project Phoenix")
    assert not off.can_file_in_group("Finance")


def test_review_decide_group_alone_filed_into_empty_group(tmp_path: Path) -> None:
    root = _library(tmp_path, on=True)
    (root / "_sorting" / "unknown.md").write_text("Nothing recognisable here.", encoding="utf-8")
    session = _review(root)
    (item,) = session.items

    assert session.decide(item, ("Finance",)) is None
    outcome = session.commit()

    assert (root / "Finance" / "unknown.md").is_file()
    assert outcome.into_empty_groups == 1


def test_review_decide_group_alone_refused_when_off(tmp_path: Path) -> None:
    root = _library(tmp_path, on=False)
    (root / "_sorting" / "unknown.md").write_text("Nothing recognisable here.", encoding="utf-8")
    session = _review(root)
    (item,) = session.items

    assert session.decide(item, ("Finance",)) is not None


def test_review_group_alone_refused_once_a_category_is_planned(tmp_path: Path) -> None:
    root = _library(tmp_path, on=True)
    (root / "_sorting" / "unknown.md").write_text("Nothing recognisable here.", encoding="utf-8")
    session = _review(root)
    (item,) = session.items
    session.add_folder(("Finance",), "Budgets")

    assert not session.can_file_in_group("Finance")
    assert session.decide(item, ("Finance",)) is not None


# endregion

# region Reclassify


@pytest.mark.parametrize("on", [True, False])
def test_run_reclassify_file_in_empty_group_kept_when_on(tmp_path: Path, on: bool) -> None:
    root = _library(tmp_path, on=on)
    (root / "Finance" / "budget.md").write_text(_FINANCE_NOTE, encoding="utf-8")

    (proposal,) = run_reclassify(Library(root))

    assert (proposal.action == "keep") is on


# endregion
