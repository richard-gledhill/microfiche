"""Tests for learning keyword hints from the documents a person filed by hand in ``review``."""

import json
from pathlib import Path

import pytest
from microfiche.core import learning
from microfiche.core.learning import LearnedHint, learn_hints
from microfiche.core.ledger import Ledger
from microfiche.core.library.library import Library
from microfiche.core.library.library_file import LIBRARY_FILENAME, load_library_file
from microfiche.core.models.ledger import LedgerRecord
from microfiche.core.organizer import run_sort
from microfiche.core.review import ReviewSession

# region Test helpers


_BILLS = "Bills"
_REPORTS = "Reports"
_PEOPLE = "Invoice from Alpha Ltd. Please send the remittance advice. Reference {n}."


def _library(tmp_path: Path, *, enabled: bool = True, min_decisions: int = 3, cap: int = 3) -> Path:
    root = tmp_path / "library"
    for category in (_BILLS, _REPORTS):
        (root / "Finance" / category).mkdir(parents=True)
    (root / "_sorting").mkdir()
    (root / ".microfiche").mkdir()
    (root / ".microfiche" / "microfiche-config.toml").write_text(
        f"[learning]\nenabled = {str(enabled).lower()}\nmin_decisions = {min_decisions}\nmax_hints_per_run = {cap}\n",
        encoding="utf-8",
    )
    return root


def _library_file(root: Path, groups: list[dict[str, object]]) -> None:
    (root / ".microfiche" / LIBRARY_FILENAME).write_text(json.dumps({"groups": groups}), encoding="utf-8")


def _filed(root: Path, category: str, name: str, text: str, *, by: str = "user") -> None:
    """A document in ``Finance/<category>`` that the ledger says was filed by ``by``."""

    path = root / "Finance" / category / name
    path.write_text(text, encoding="utf-8")
    Ledger(root / ".microfiche").append([
        LedgerRecord(
            event="filed",
            job_id="job0",
            path=f"Finance/{category}/{name}",
            original_path=f"_sorting/{name}",
            content_hash=name,
            unit_type="file",
            group="Finance",
            category=category,
            classified_by=by,
        )
    ])


def _bills(root: Path, count: int = 3, text: str = _PEOPLE) -> None:
    for number in range(count):
        _filed(root, _BILLS, f"inv{number}.md", text.format(n=f"unique{'x' * number}"))


def _learn(root: Path, job_id: str = "job1") -> list[LearnedHint]:
    return learn_hints(Library(root), {("Finance", _BILLS)}, job_id)


def _learned_in_file(root: Path) -> list[str]:
    library_file = load_library_file(root / ".microfiche", 2)
    return library_file.learned_hints_for("Finance", _BILLS)


# endregion

# region Learn hints


def test_learn_hints_off_by_default_changes_nothing(tmp_path: Path) -> None:
    root = _library(tmp_path, enabled=False)
    _bills(root)

    assert _learn(root) == []
    assert not (root / ".microfiche" / LIBRARY_FILENAME).exists()


def test_learn_hints_adds_word_most_user_documents_share(tmp_path: Path) -> None:
    root = _library(tmp_path)
    _bills(root)

    learned = _learn(root)

    assert LearnedHint("Finance", _BILLS, "remittance") in learned
    assert "remittance" in _learned_in_file(root)


def test_learn_hints_below_minimum_decisions_learns_nothing(tmp_path: Path) -> None:
    root = _library(tmp_path, min_decisions=3)
    _bills(root, count=2)

    assert _learn(root) == []


def test_learn_hints_counts_only_documents_the_user_filed(tmp_path: Path) -> None:
    root = _library(tmp_path)
    _bills(root, count=2)
    _filed(root, _BILLS, "auto.md", _PEOPLE.format(n="auto"), by="rules_engine")

    assert _learn(root) == []


def test_learn_hints_word_in_sibling_category_not_learned(tmp_path: Path) -> None:
    root = _library(tmp_path)
    _bills(root)
    _filed(root, _REPORTS, "annual.md", "The annual report lists every remittance made.", by="rules_engine")

    words = {hint.hint for hint in _learn(root)}

    assert "remittance" not in words


def test_learn_hints_skips_common_short_and_name_words(tmp_path: Path) -> None:
    root = _library(tmp_path)
    _bills(root, text="Bills about the finance, due now. Pay it. Reference {n}. Zebra.")

    words = {hint.hint for hint in _learn(root)}

    assert words == {
        "zebra",
        "reference",
    }  # not "bills" / "finance" (names), "about" / "the" (common), "pay" / "due" (short)


def test_learn_hints_known_hints_not_repeated_and_user_hints_untouched(tmp_path: Path) -> None:
    root = _library(tmp_path)
    _library_file(root, [{"name": "Finance", "children": [{"name": _BILLS, "hints": ["Remittance", "invoice"]}]}])
    _bills(root)

    words = {hint.hint for hint in _learn(root)}

    assert "remittance" not in words
    assert "invoice" not in words
    library_file = load_library_file(root / ".microfiche", 2)
    assert library_file.hints_for("Finance", _BILLS)[:2] == ["Remittance", "invoice"]
    node = next(c for g in library_file.groups for c in g.children if c.name == _BILLS)
    assert node.hints == ["Remittance", "invoice"]  # the user's own, in the order they wrote them


def test_learn_hints_caps_hints_per_category_per_run(tmp_path: Path) -> None:
    root = _library(tmp_path, cap=2)
    _bills(root, text="alpha bravo charlie delta echo foxtrot {n}")

    assert len(_learn(root)) == 2


def test_learn_hints_creates_a_specific_entry_beside_a_wildcard(tmp_path: Path) -> None:
    root = _library(tmp_path)
    _library_file(root, [{"name": "*", "children": [{"name": "*", "description": "anything"}]}])
    _bills(root)

    _learn(root)

    library_file = load_library_file(root / ".microfiche", 2)
    assert [group.name for group in library_file.groups] == ["*", "Finance"]
    assert "remittance" in library_file.learned_hints_for("Finance", _BILLS)


def test_learn_hints_deleted_hint_is_not_learned_again(tmp_path: Path) -> None:
    root = _library(tmp_path)
    _bills(root)
    assert "remittance" in {hint.hint for hint in _learn(root)}
    library_file = load_library_file(root / ".microfiche", 2)
    # The person deletes every learned hint from the file.
    (root / ".microfiche" / LIBRARY_FILENAME).write_text(
        json.dumps({"groups": [{"name": "Finance", "children": [{"name": _BILLS}]}]}), encoding="utf-8"
    )
    assert library_file.learned_hints_for("Finance", _BILLS)

    again = {hint.hint for hint in _learn(root, "job2")}

    assert "remittance" not in again


def test_learn_hints_records_each_hint_in_the_ledger(tmp_path: Path) -> None:
    root = _library(tmp_path)
    _bills(root)

    _learn(root)

    assert ("Finance", _BILLS, "remittance") in Ledger(root / ".microfiche").learned_hints()
    assert len(Ledger(root / ".microfiche").current()) == 3  # the events are not filed documents


def test_learn_hints_failed_write_learns_nothing_and_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _library(tmp_path)
    _bills(root)

    def refuse(path: Path, library_file: object) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(learning, "write_library_file", refuse)

    assert _learn(root) == []
    assert Ledger(root / ".microfiche").learned_hints() == set()


# endregion

# region Used by the rules and reported


def test_run_sort_learned_hint_files_a_matching_document_and_is_counted(tmp_path: Path) -> None:
    root = _library(tmp_path)
    _bills(root)
    _learn(root)
    (root / "_sorting" / "new.md").write_text("Finance: please send the remittance today.", encoding="utf-8")

    report = run_sort(Library(root))

    assert (root / "Finance" / _BILLS / "new.md").is_file()
    assert report.by_learned_hint == 1
    ((_, classification),) = report.filed
    assert classification.category is not None
    assert classification.category.reason.startswith("Learned keyword hint 'remittance'")


# endregion

# region Review commit


def test_review_commit_learns_from_the_choices_made(tmp_path: Path) -> None:
    root = _library(tmp_path)
    for number in range(3):
        (root / "_sorting" / f"doc{number}.md").write_text(_PEOPLE.format(n=f"ref{number}x"), encoding="utf-8")
    session = ReviewSession.start(Library(root))
    for item in session.items:
        assert session.decide(item, ("Finance", _BILLS)) is None

    outcome = session.commit()

    assert "remittance" in {hint.hint for hint in outcome.learned}
    assert "remittance" in _learned_in_file(root)


def test_review_commit_learning_off_learns_nothing(tmp_path: Path) -> None:
    root = _library(tmp_path, enabled=False)
    for number in range(3):
        (root / "_sorting" / f"doc{number}.md").write_text(_PEOPLE.format(n=f"ref{number}x"), encoding="utf-8")
    session = ReviewSession.start(Library(root))
    for item in session.items:
        session.decide(item, ("Finance", _BILLS))

    assert session.commit().learned == []


# endregion
