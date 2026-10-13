"""Tests for finding inbox files that are exact copies of a file already in the library."""

import os
from pathlib import Path
from typing import Literal

import pytest
from microfiche.core import duplicates
from microfiche.core.duplicates import DuplicateIndex, ExistingCopy
from microfiche.core.library.library import Library
from microfiche.core.models.classification import CategoryMatch, ClassificationResult, GroupMatch
from microfiche.core.models.document import Document
from microfiche.core.models.unit import SortableUnit

# region Test helpers


GROUP = "Project Phoenix"
ARCHITECTURE = "02 Architecture"
RESEARCH = "03 Research"
TEXT = "Project Phoenix architecture decisions."


def _library(tmp_path: Path) -> Library:
    root = tmp_path / "library"
    (root / GROUP / ARCHITECTURE).mkdir(parents=True)
    (root / GROUP / RESEARCH).mkdir(parents=True)
    (root / "_sorting").mkdir()
    return Library(root)


def _write(path: Path, text: str = TEXT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _inbox(library: Library, name: str = "note.md", text: str = TEXT) -> Path:
    return _write(library.inbox / name, text)


def _unit(path: Path, kind: Literal["file", "folder"] = "file") -> SortableUnit:
    document = Document(file_path=path, file_name=path.name, extension=path.suffix, content="")
    return SortableUnit(source_path=path, kind=kind, documents=[document])


def _classified(
    category: str | None = ARCHITECTURE, group: str | None = GROUP, *, confident: bool = True
) -> ClassificationResult:
    return ClassificationResult(
        group=GroupMatch(name=group, confidence=1.0, reason="group reason"),
        category=CategoryMatch(name=category, confidence=0.9, reason="category reason"),
        overall_confidence=0.9 if confident else 0.5,
        classified_by="rules_engine",
        confident=confident,
    )


@pytest.fixture
def hash_calls(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Every path hashed, in order, while the test runs."""

    calls: list[Path] = []
    real = duplicates.file_hash

    def counting(path: Path) -> str:
        calls.append(path)
        return real(path)

    monkeypatch.setattr(duplicates, "file_hash", counting)
    return calls


# endregion


# region Public API


# region DuplicateIndex.find


def test_find_copy_anywhere_in_library(tmp_path: Path) -> None:
    library = _library(tmp_path)
    existing = _write(library.root / GROUP / RESEARCH / "older-name.md")
    inbox = _inbox(library)

    assert DuplicateIndex(library).find(inbox) == [ExistingCopy(existing)]


def test_find_same_name_different_content_not_a_copy(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library.root / GROUP / ARCHITECTURE / "note.md", "Something else entirely.")
    inbox = _inbox(library, "note.md")

    assert DuplicateIndex(library).find(inbox) == []


def test_find_same_size_different_content_not_a_copy(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library.root / GROUP / ARCHITECTURE / "other.md", "x" * len(TEXT))
    inbox = _inbox(library)

    assert DuplicateIndex(library).find(inbox) == []


def test_find_several_copies_listed_in_path_order(tmp_path: Path) -> None:
    library = _library(tmp_path)
    second = _write(library.root / GROUP / RESEARCH / "b.md")
    first = _write(library.root / GROUP / ARCHITECTURE / "a.md")

    assert DuplicateIndex(library).find(_inbox(library)) == [ExistingCopy(first), ExistingCopy(second)]


def test_find_hashes_only_same_size_candidates(tmp_path: Path, hash_calls: list[Path]) -> None:
    library = _library(tmp_path)
    same_size = _write(library.root / GROUP / ARCHITECTURE / "same-size.md", "y" * len(TEXT))
    copy = _write(library.root / GROUP / RESEARCH / "copy.md")
    _write(library.root / GROUP / RESEARCH / "short.md", "tiny")
    _write(library.root / GROUP / RESEARCH / "long.md", TEXT * 50)
    inbox = _inbox(library)

    DuplicateIndex(library).find(inbox)

    assert sorted(hash_calls) == sorted([inbox, same_size, copy])


def test_find_no_same_size_file_hashes_nothing(tmp_path: Path, hash_calls: list[Path]) -> None:
    library = _library(tmp_path)
    _write(library.root / GROUP / ARCHITECTURE / "short.md", "tiny")

    assert DuplicateIndex(library).find(_inbox(library)) == []
    assert hash_calls == []


def test_find_hashes_each_file_once(tmp_path: Path, hash_calls: list[Path]) -> None:
    library = _library(tmp_path)
    _write(library.root / GROUP / RESEARCH / "copy.md")
    inbox = _inbox(library)
    index = DuplicateIndex(library)

    index.find(inbox)
    index.find(inbox)

    assert len(hash_calls) == len(set(hash_calls)) == 2


def test_find_skips_inbox_state_folder_and_excluded_folders(tmp_path: Path) -> None:
    library = _library(tmp_path)
    library.config.exclusions.exclude = ["_*", ".*"]
    _write(library.root / "_archive" / "copy.md")  # excluded by pattern
    _write(library.root / ".obsidian" / "copy.md")  # excluded by pattern
    _write(library.state_dir / "copy.md")
    _write(library.inbox / "another-inbox-file.md")
    inbox = _inbox(library)

    assert DuplicateIndex(library).find(inbox) == []


def test_find_empty_files_are_never_copies(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library.root / GROUP / ARCHITECTURE / ".gitkeep", "")
    inbox = _inbox(library, "empty.md", "")

    assert DuplicateIndex(library).find(inbox) == []


def test_find_missing_file_has_no_copies(tmp_path: Path) -> None:
    library = _library(tmp_path)

    assert DuplicateIndex(library).find(library.inbox / "gone.md") == []


def test_find_reads_nothing_until_first_needed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    walked: list[object] = []
    real = os.scandir
    monkeypatch.setattr(duplicates.os, "scandir", lambda path: walked.append(path) or real(path))
    index = DuplicateIndex(library)

    assert walked == []
    index.find(_inbox(library, "empty.md", ""))  # an empty file needs no walk
    assert walked == []
    index.find(_inbox(library))
    assert walked  # the library is walked, once, when a real file is checked


def test_find_walks_library_once_for_many_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    index = DuplicateIndex(library)
    index.find(_inbox(library, "a.md"))
    walked: list[object] = []
    real = os.scandir
    monkeypatch.setattr(duplicates.os, "scandir", lambda path: walked.append(path) or real(path))

    index.find(_inbox(library, "b.md", "other text"))

    assert walked == []


def test_find_unreadable_folder_skipped_not_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    copy = _write(library.root / GROUP / ARCHITECTURE / "copy.md")
    locked_folder = library.root / GROUP / RESEARCH
    _write(locked_folder / "hidden-copy.md")
    inbox = _inbox(library)
    real = os.scandir

    def scandir(path: str | os.PathLike[str]) -> object:
        if Path(path) == locked_folder:
            raise PermissionError(path)
        return real(path)

    monkeypatch.setattr(duplicates.os, "scandir", scandir)

    assert DuplicateIndex(library).find(inbox) == [ExistingCopy(copy)]


def test_find_unreadable_inbox_file_has_no_copies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    _write(library.root / GROUP / ARCHITECTURE / "copy.md")
    inbox = _inbox(library)

    def locked(path: Path) -> str:
        raise PermissionError(path)

    monkeypatch.setattr(duplicates, "file_hash", locked)

    assert DuplicateIndex(library).find(inbox) == []


def test_find_unreadable_candidate_treated_as_not_a_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    locked = _write(library.root / GROUP / ARCHITECTURE / "locked.md")
    good = _write(library.root / GROUP / RESEARCH / "good.md")
    inbox = _inbox(library)
    real = duplicates.file_hash

    def hash_unless_locked(path: Path) -> str:
        if path == locked:
            raise PermissionError(path)
        return real(path)

    monkeypatch.setattr(duplicates, "file_hash", hash_unless_locked)

    assert DuplicateIndex(library).find(inbox) == [ExistingCopy(good)]


# endregion


# region DuplicateIndex.add


def test_add_registers_file_so_identical_one_is_a_copy(tmp_path: Path) -> None:
    library = _library(tmp_path)
    index = DuplicateIndex(library)
    first = _inbox(library, "first.md")
    second = _inbox(library, "second.md")
    destination = library.root / GROUP / ARCHITECTURE / "first.md"

    index.add(first, destination)

    assert index.find(second) == [ExistingCopy(destination, pending_from=first)]


def test_add_different_content_not_a_copy(tmp_path: Path) -> None:
    library = _library(tmp_path)
    index = DuplicateIndex(library)
    index.add(_inbox(library, "first.md"), library.root / GROUP / ARCHITECTURE / "first.md")

    assert index.find(_inbox(library, "second.md", "Something else entirely.")) == []


def test_add_library_copies_listed_before_pending(tmp_path: Path) -> None:
    library = _library(tmp_path)
    existing = _write(library.root / GROUP / RESEARCH / "old.md")
    index = DuplicateIndex(library)
    first = _inbox(library, "first.md")
    destination = library.root / GROUP / ARCHITECTURE / "first.md"
    index.add(first, destination)

    copies = index.find(_inbox(library, "second.md"))

    assert copies == [ExistingCopy(existing), ExistingCopy(destination, pending_from=first)]


# endregion


# region DuplicateIndex.check


def test_check_folder_unit_never_a_duplicate(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library.root / GROUP / ARCHITECTURE / "a.md")
    folder = library.inbox / "bundle"
    _write(folder / "a.md")

    assert DuplicateIndex(library).check(_unit(folder, "folder"), _classified()) is None


def test_check_no_copy_returns_none(tmp_path: Path) -> None:
    library = _library(tmp_path)

    assert DuplicateIndex(library).check(_unit(_inbox(library)), _classified()) is None


def test_check_duplicate_carries_unit_classification_and_copy(tmp_path: Path) -> None:
    library = _library(tmp_path)
    existing = _write(library.root / GROUP / ARCHITECTURE / "note.md")
    unit, classification = _unit(_inbox(library)), _classified()

    duplicate = DuplicateIndex(library).check(unit, classification)

    assert duplicate is not None
    assert (duplicate.unit, duplicate.classification, duplicate.existing) == (unit, classification, existing)


def test_check_reason_copy_at_destination(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library.root / GROUP / ARCHITECTURE / "note.md")

    duplicate = DuplicateIndex(library).check(_unit(_inbox(library)), _classified())

    assert duplicate is not None
    assert duplicate.reason == "identical to Project Phoenix/02 Architecture/note.md, already filed where this would go"


@pytest.mark.parametrize("relative", ["other-name.md", "bundle/note.md"])
def test_check_reason_copy_in_destination_folder(tmp_path: Path, relative: str) -> None:
    library = _library(tmp_path)
    _write(library.root / GROUP / ARCHITECTURE / relative)

    duplicate = DuplicateIndex(library).check(_unit(_inbox(library)), _classified())

    assert duplicate is not None
    assert duplicate.reason == (
        f"identical to Project Phoenix/02 Architecture/{relative}, in the folder this would be filed to"
    )


@pytest.mark.parametrize("where", [f"{GROUP}/{RESEARCH}/note.md", "Other Project/02 Architecture/note.md"])
def test_check_reason_copy_in_other_category_or_group_names_where_it_would_go(tmp_path: Path, where: str) -> None:
    library = _library(tmp_path)
    _write(library.root / where)

    duplicate = DuplicateIndex(library).check(_unit(_inbox(library)), _classified())

    assert duplicate is not None
    assert duplicate.reason == f"identical to {where}; this would be filed in Project Phoenix/02 Architecture"


def test_check_reason_not_confident_names_suggestion(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library.root / GROUP / RESEARCH / "note.md")

    duplicate = DuplicateIndex(library).check(_unit(_inbox(library)), _classified(confident=False))

    assert duplicate is not None
    assert duplicate.reason == (
        "identical to Project Phoenix/03 Research/note.md; "
        "the classifier suggests Project Phoenix/02 Architecture but is not confident"
    )


@pytest.mark.parametrize(("category", "group"), [(None, None), (None, GROUP)])
def test_check_reason_unresolved(tmp_path: Path, category: str | None, group: str | None) -> None:
    library = _library(tmp_path)
    _write(library.root / GROUP / RESEARCH / "note.md")

    duplicate = DuplicateIndex(library).check(_unit(_inbox(library)), _classified(category, group, confident=False))

    assert duplicate is not None
    assert duplicate.reason == "identical to Project Phoenix/03 Research/note.md; could not be classified"


def test_check_reason_copy_being_filed_this_run(tmp_path: Path) -> None:
    library = _library(tmp_path)
    index = DuplicateIndex(library)
    index.add(_inbox(library, "first.md"), library.root / GROUP / ARCHITECTURE / "first.md")

    duplicate = index.check(_unit(_inbox(library, "second.md")), _classified())

    assert duplicate is not None
    assert duplicate.existing == library.root / GROUP / ARCHITECTURE / "first.md"
    assert (
        duplicate.reason == "identical to 'first.md', which is being filed this run to Project Phoenix/02 Architecture"
    )


def test_check_prefers_copy_at_destination_then_destination_folder(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library.root / "Another Project" / "a-first-in-path-order.md")
    in_folder = _write(library.root / GROUP / ARCHITECTURE / "other-name.md")
    unit = _unit(_inbox(library))

    chosen = DuplicateIndex(library).check(unit, _classified())
    assert chosen is not None
    assert chosen.existing == in_folder

    at_destination = _write(library.root / GROUP / ARCHITECTURE / "note.md")
    chosen = DuplicateIndex(library).check(unit, _classified())
    assert chosen is not None
    assert chosen.existing == at_destination


def test_check_prefers_library_copy_over_one_about_to_be_filed(tmp_path: Path) -> None:
    library = _library(tmp_path)
    existing = _write(library.root / GROUP / RESEARCH / "old.md")
    index = DuplicateIndex(library)
    index.add(_inbox(library, "first.md"), library.root / GROUP / ARCHITECTURE / "first.md")

    duplicate = index.check(_unit(_inbox(library, "second.md")), _classified())

    assert duplicate is not None
    assert duplicate.existing == existing


# endregion


# endregion
