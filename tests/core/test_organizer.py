"""Tests for the `sort` pipeline: scan -> classify -> file as one job, leaving the rest for review."""

import shutil
from pathlib import Path

import pytest
from core.config import MICROFICHE_DIRNAME
from core.filer import AUDIT_LOG_FILENAME, rollback_job
from core.ledger import Ledger
from core.library.library import Library
from core.organizer import run_sort
from core.utils.hashing import file_hash

_MOCK_LIBRARY = Path(__file__).resolve().parents[1] / "mock_library"

# In the mock library, this note names "Project Phoenix" and "architecture", so it files
# confidently; the solar note names no known group, so it must go to review.
_PHOENIX_NOTE = "PhoenixArchitectureNotes.md"
_SOLAR_NOTE = "SolarConstructionNotes.md"
_PHOENIX_DESTINATION = Path("Project Phoenix") / "02 Architecture" / _PHOENIX_NOTE


# The mock library's inbox also holds a folder of three Project Phoenix documents (two architecture, one
# research). Most tests here are about the two loose notes above, so `_library` leaves it out unless asked.
_PACK = "phoenix-weekly-pack"
_ARCHITECTURE_DIR = Path("Project Phoenix") / "02 Architecture"
_RESEARCH_DIR = Path("Project Phoenix") / "03 Research"
_PACK_FILES = {
    "architecture-decision-log.md": _ARCHITECTURE_DIR,
    "component-diagram-notes.md": _ARCHITECTURE_DIR,
    "research-summary.md": _RESEARCH_DIR,
}


def _library(tmp_path: Path, *, with_pack: bool = False) -> Path:
    library = tmp_path / "library"
    shutil.copytree(_MOCK_LIBRARY, library)
    if not with_pack:
        shutil.rmtree(library / "_sorting" / _PACK)
    return library


def _folders(library: Path) -> set[str]:
    """Library-relative path of every folder outside microfiche's own state."""

    state_dir = library / MICROFICHE_DIRNAME
    return {
        path.relative_to(library).as_posix()
        for path in library.rglob("*")
        if path.is_dir() and not path.is_relative_to(state_dir)
    }


def _snapshot(library: Path) -> dict[str, str]:
    """Library-relative path -> hash for every file, ignoring microfiche's own state."""

    state_dir = library / MICROFICHE_DIRNAME
    return {
        path.relative_to(library).as_posix(): file_hash(path)
        for path in sorted(library.rglob("*"))
        if path.is_file() and not path.is_relative_to(state_dir)
    }


def test_run_sort_files_confident_units_leaves_rest_for_review(tmp_path: Path) -> None:
    library = _library(tmp_path)

    report = run_sort(Library(library))

    assert [unit.source_path.name for unit, _ in report.filed] == [_PHOENIX_NOTE]
    assert [unit.source_path.name for unit, _ in report.needs_review] == [_SOLAR_NOTE]
    assert (library / _PHOENIX_DESTINATION).exists()
    assert not (library / "_sorting" / _PHOENIX_NOTE).exists()
    assert (library / "_sorting" / _SOLAR_NOTE).exists()


def test_run_sort_records_one_job_for_all_filed(tmp_path: Path) -> None:
    library = _library(tmp_path)

    report = run_sort(Library(library))

    assert report.job is not None
    assert [move.new_path for move in report.job.moves] == [library / _PHOENIX_DESTINATION]
    assert report.audit_events == report.job.moves
    assert (library / MICROFICHE_DIRNAME / "rollback" / f"job_{report.job.job_id}.json").exists()
    (record,) = Ledger(library / MICROFICHE_DIRNAME).current()
    assert record.job_id == report.job.job_id
    assert record.path == _PHOENIX_DESTINATION.as_posix()
    assert (record.group, record.category) == ("Project Phoenix", "02 Architecture")
    assert (library / MICROFICHE_DIRNAME / AUDIT_LOG_FILENAME).read_text(encoding="utf-8").count("\n") == 1


def test_run_sort_review_units_not_moved_or_recorded(tmp_path: Path) -> None:
    library = _library(tmp_path)

    run_sort(Library(library))

    recorded = [record.original_path for record in Ledger(library / MICROFICHE_DIRNAME).read_all()]
    assert recorded == [f"_sorting/{_PHOENIX_NOTE}"]


def test_run_sort_nothing_confident_writes_no_state(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / "_sorting" / _PHOENIX_NOTE).unlink()
    before = _snapshot(library)

    report = run_sort(Library(library))

    assert report.job is None
    assert report.filed == []
    assert report.audit_events == []
    assert [unit.source_path.name for unit, _ in report.needs_review] == [_SOLAR_NOTE]
    assert _snapshot(library) == before
    state_dir = library / MICROFICHE_DIRNAME
    assert not (state_dir / "rollback").exists()
    assert not (state_dir / AUDIT_LOG_FILENAME).exists()
    assert not Ledger(state_dir).path.exists()


def test_run_sort_no_inbox_does_nothing(tmp_path: Path) -> None:
    library = _library(tmp_path)
    shutil.rmtree(library / "_sorting")

    report = run_sort(Library(library))

    assert report.job is None
    assert report.filed == []
    assert report.needs_review == []


def test_run_sort_keep_folders_files_folder_whole(tmp_path: Path) -> None:
    library = _library(tmp_path)
    bundle = library / "_sorting" / "phoenix-bundle"
    bundle.mkdir()
    (bundle / "overview.md").write_text("Project Phoenix architecture overview.", encoding="utf-8")
    (bundle / "decisions.md").write_text("Project Phoenix architecture decisions.", encoding="utf-8")

    report = run_sort(Library(library), keep_folders=True)

    destination = library / "Project Phoenix" / "02 Architecture" / "phoenix-bundle"
    assert (destination / "overview.md").exists()
    assert (destination / "decisions.md").exists()
    assert not bundle.exists()
    assert report.job is not None
    folder_records = [r for r in Ledger(library / MICROFICHE_DIRNAME).current() if r.unit_type == "folder"]
    assert [r.path for r in folder_records] == ["Project Phoenix/02 Architecture/phoenix-bundle"]


def test_run_sort_rollback_restores_library(tmp_path: Path) -> None:
    library = _library(tmp_path)
    before = _snapshot(library)
    report = run_sort(Library(library))
    assert report.job is not None
    assert _snapshot(library) != before

    rollback_job(Library(library), report.job.job_id)

    assert _snapshot(library) == before
    assert Ledger(library / MICROFICHE_DIRNAME).current() == []


_ARCHITECTURE_TEXT = "Project Phoenix architecture decisions."


def test_run_sort_destination_taken_reviews_only_that_unit(tmp_path: Path) -> None:
    library = _library(tmp_path)
    taken = library / _PHOENIX_DESTINATION
    taken.write_text("already filed here", encoding="utf-8")
    (library / "_sorting" / "other.md").write_text(_ARCHITECTURE_TEXT, encoding="utf-8")

    report = run_sort(Library(library))

    assert [unit.source_path.name for unit, _ in report.filed] == ["other.md"]
    needs_review = {unit.source_path.name: classification for unit, classification in report.needs_review}
    assert set(needs_review) == {_PHOENIX_NOTE, _SOLAR_NOTE}
    assert f"'{_PHOENIX_NOTE}' already exists in Project Phoenix/02 Architecture" in (
        needs_review[_PHOENIX_NOTE].category.reason
    )
    assert taken.read_text(encoding="utf-8") == "already filed here"  # never overwritten
    assert (library / "_sorting" / _PHOENIX_NOTE).exists()  # left in the inbox
    assert (library / "Project Phoenix" / "02 Architecture" / "other.md").exists()


def test_run_sort_destination_taken_keeps_proposed_group_category(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / _PHOENIX_DESTINATION).write_text("already filed here", encoding="utf-8")

    report = run_sort(Library(library))

    held = {unit.source_path.name: classification for unit, classification in report.needs_review}[_PHOENIX_NOTE]
    assert (held.group.name, held.category.name) == ("Project Phoenix", "02 Architecture")
    assert held.confident is False
    assert held.category.reason.startswith("Category name '02 Architecture'")  # why it matched is kept


def test_run_sort_same_destination_in_run_files_first_reviews_second(tmp_path: Path) -> None:
    library = _library(tmp_path)
    lib = Library(library)
    lib.config.naming_rules.rules = {r"^draft-\d+": "final"}  # both names become final.md
    (library / "_sorting" / "draft-1.md").write_text(_ARCHITECTURE_TEXT, encoding="utf-8")
    # Different content from draft-1, so they are a name collision and not duplicates.
    (library / "_sorting" / "draft-2.md").write_text(_ARCHITECTURE_TEXT + " Second draft.", encoding="utf-8")

    report = run_sort(lib)

    filed = [unit.source_path.name for unit, _ in report.filed]
    assert "draft-1.md" in filed
    assert "draft-2.md" not in filed
    needs_review = {unit.source_path.name: classification for unit, classification in report.needs_review}
    assert "another unit in this run is already going to Project Phoenix/02 Architecture/final.md" in (
        needs_review["draft-2.md"].category.reason
    )
    assert (library / "Project Phoenix" / "02 Architecture" / "final.md").exists()
    assert (library / "_sorting" / "draft-2.md").exists()


# "user story" is a keyword hint for 01 Requirements, which scores 0.75: it files at the default
# threshold (0.75), and is left for review if the library raises the threshold above it.
_HINT_ONLY_TEXT = "Project Phoenix user story backlog."


def test_run_sort_default_threshold_files_keyword_hint(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / "_sorting" / "backlog.md").write_text(_HINT_ONLY_TEXT, encoding="utf-8")

    report = run_sort(Library(library))

    assert "backlog.md" in [unit.source_path.name for unit, _ in report.filed]
    assert (library / "Project Phoenix" / "01 Requirements" / "backlog.md").exists()


def test_run_sort_raised_threshold_reviews_keyword_hint(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / "_sorting" / "backlog.md").write_text(_HINT_ONLY_TEXT, encoding="utf-8")
    lib = Library(library)
    lib.config.classification.confidence_threshold = 0.8

    report = run_sort(lib)

    assert "backlog.md" in [unit.source_path.name for unit, _ in report.needs_review]
    assert (library / "_sorting" / "backlog.md").exists()


def test_run_sort_unreadable_file_does_not_stop_rest(tmp_path: Path) -> None:
    """Regression: a corrupt file used to raise out of the scan, so nothing at all was filed."""

    library = _library(tmp_path)
    broken = library / "_sorting" / "broken.docx"
    broken.write_text("this is not a zip file", encoding="utf-8")

    report = run_sort(Library(library))

    assert [unit.source_path.name for unit, _ in report.filed] == [_PHOENIX_NOTE]
    needs_review = {unit.source_path.name: classification for unit, classification in report.needs_review}
    assert set(needs_review) == {_SOLAR_NOTE, "broken.docx"}
    assert needs_review["broken.docx"].category.reason.startswith("Could not read 'broken.docx':")
    assert broken.exists()  # left in the inbox, untouched
    assert (library / _PHOENIX_DESTINATION).exists()
    assert report.job is not None
    assert [move.new_path for move in report.job.moves] == [library / _PHOENIX_DESTINATION]


def test_run_sort_only_unreadable_file_writes_no_job(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / "_sorting" / _PHOENIX_NOTE).unlink()
    (library / "_sorting" / _SOLAR_NOTE).unlink()
    (library / "_sorting" / "broken.docx").write_text("not a zip", encoding="utf-8")

    report = run_sort(Library(library))

    assert report.job is None
    assert [unit.source_path.name for unit, _ in report.needs_review] == ["broken.docx"]
    assert not (library / MICROFICHE_DIRNAME / "rollback").exists()


# region Inbox folders (keep_folders on and off)


def test_run_sort_folder_kept_whole_files_under_dominant_category(tmp_path: Path) -> None:
    library = _library(tmp_path, with_pack=True)

    report = run_sort(Library(library), keep_folders=True)

    assert (library / _ARCHITECTURE_DIR / _PACK).is_dir()  # two documents vote architecture, one research
    assert {path.name for path in (library / _ARCHITECTURE_DIR / _PACK).iterdir()} == set(_PACK_FILES)
    assert not (library / "_sorting" / _PACK).exists()
    assert report.job is not None
    folder_records = [r for r in Ledger(library / MICROFICHE_DIRNAME).current() if r.unit_type == "folder"]
    assert [r.path for r in folder_records] == [(_ARCHITECTURE_DIR / _PACK).as_posix()]
    assert report.folders_removed == []  # it moved whole; there is no emptied folder to remove


def test_run_sort_folders_off_files_each_document_separately(tmp_path: Path) -> None:
    library = _library(tmp_path, with_pack=True)

    report = run_sort(Library(library), keep_folders=False)

    for name, folder in _PACK_FILES.items():
        assert (library / folder / name).exists()
    filed = {unit.source_path.name for unit, _ in report.filed}
    assert set(_PACK_FILES) <= filed
    records = [
        r for r in Ledger(library / MICROFICHE_DIRNAME).current() if r.original_path.startswith("_sorting/phoenix")
    ]
    assert sorted(r.path for r in records) == sorted((folder / name).as_posix() for name, folder in _PACK_FILES.items())
    assert report.job is not None
    assert {r.job_id for r in records} == {report.job.job_id}  # one job for all three


def test_run_sort_folders_off_emptied_folder_removed_and_rollback_restores(tmp_path: Path) -> None:
    library = _library(tmp_path, with_pack=True)
    before_files, before_folders = _snapshot(library), _folders(library)

    report = run_sort(Library(library), keep_folders=False)

    assert not (library / "_sorting" / _PACK).exists()
    assert report.folders_removed == [library / "_sorting" / _PACK]
    assert report.folders_kept == []
    assert report.job is not None
    assert [e.original_path for e in report.job.moves if e.action == "remove_folder"] == [library / "_sorting" / _PACK]
    audit = (library / MICROFICHE_DIRNAME / AUDIT_LOG_FILENAME).read_text(encoding="utf-8")
    assert f"remove_folder _sorting/{_PACK} -> -" in audit

    rollback_job(Library(library), report.job.job_id)

    assert _snapshot(library) == before_files
    assert _folders(library) == before_folders  # the emptied folder is back
    assert f"restore_folder _sorting/{_PACK} -> -" in (library / MICROFICHE_DIRNAME / AUDIT_LOG_FILENAME).read_text(
        encoding="utf-8"
    )


def test_run_sort_folders_off_nested_empty_folders_removed_and_restored(tmp_path: Path) -> None:
    library = _library(tmp_path)
    nested = library / "_sorting" / "outer" / "inner"
    nested.mkdir(parents=True)
    (nested / "deep.md").write_text(_ARCHITECTURE_TEXT, encoding="utf-8")
    before_folders = _folders(library)

    report = run_sort(Library(library), keep_folders=False)

    assert (library / _ARCHITECTURE_DIR / "deep.md").exists()
    assert not (library / "_sorting" / "outer").exists()  # inner first, then outer
    assert report.job is not None
    removed = [e.original_path for e in report.job.moves if e.action == "remove_folder"]
    assert removed == [nested, library / "_sorting" / "outer"]

    rollback_job(Library(library), report.job.job_id)

    assert (nested / "deep.md").exists()
    assert _folders(library) == before_folders


def test_run_sort_folders_off_unsupported_file_keeps_folder_and_says_why(tmp_path: Path) -> None:
    library = _library(tmp_path, with_pack=True)
    (library / "_sorting" / _PACK / "diagram.png").write_bytes(b"not a document")

    report = run_sort(Library(library), keep_folders=False)

    assert (library / "_sorting" / _PACK / "diagram.png").exists()
    assert report.job is not None
    assert not [e for e in report.job.moves if e.action == "remove_folder"]
    ((folder, reason),) = report.folders_kept
    assert folder == library / "_sorting" / _PACK
    assert reason == "it still holds diagram.png (not sorted)"
    assert report.folders_removed == []


def test_run_sort_folders_off_name_clash_between_subfolders_keeps_folder(tmp_path: Path) -> None:
    library = _library(tmp_path, with_pack=True)
    clash = library / "_sorting" / _PACK / "extra" / "architecture-decision-log.md"
    clash.parent.mkdir()
    clash.write_text("Project Phoenix architecture, a second log with the same file name.", encoding="utf-8")

    report = run_sort(Library(library), keep_folders=False)

    assert clash.exists()  # the second file with that name stays where it was
    needs_review = {unit.source_path: classification for unit, classification in report.needs_review}
    assert needs_review[clash].category.reason.endswith(
        "but another unit in this run is already going to Project Phoenix/02 Architecture/architecture-decision-log.md"
    )
    ((folder, reason),) = report.folders_kept
    assert folder == library / "_sorting" / _PACK
    assert reason == "it still holds extra/architecture-decision-log.md (needs review)"
    for name, destination in _PACK_FILES.items():
        assert (library / destination / name).exists()  # the rest of the folder was filed


def test_run_sort_folders_off_emptied_folder_that_cannot_be_removed_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _library(tmp_path)
    folder = library / "_sorting" / "bundle"
    folder.mkdir()
    (folder / "note.md").write_text(_ARCHITECTURE_TEXT, encoding="utf-8")

    def locked(self: Path, *args: object) -> None:
        raise PermissionError(self)

    monkeypatch.setattr(Path, "rmdir", locked)

    report = run_sort(Library(library), keep_folders=False)

    assert report.folders_kept == [(folder, "it could not be removed")]
    assert report.folders_removed == []


def test_run_sort_folders_off_review_document_keeps_folder(tmp_path: Path) -> None:
    library = _library(tmp_path)
    folder = library / "_sorting" / "mixed"
    folder.mkdir()
    (folder / "known.md").write_text(_ARCHITECTURE_TEXT, encoding="utf-8")
    (folder / "unknown.md").write_text("Nothing recognisable in here.", encoding="utf-8")

    report = run_sort(Library(library), keep_folders=False)

    assert (library / _ARCHITECTURE_DIR / "known.md").exists()
    assert (folder / "unknown.md").exists()
    assert report.folders_kept == [(folder, "it still holds unknown.md (needs review)")]


def test_run_sort_folders_off_nothing_filed_removes_nothing(tmp_path: Path) -> None:
    library = _library(tmp_path)
    folder = library / "_sorting" / "unknown-only"
    folder.mkdir()
    (folder / "unknown.md").write_text("Nothing recognisable in here.", encoding="utf-8")
    emptyish = library / "_sorting" / "no-documents"
    emptyish.mkdir()  # not a unit's origin, so it is not touched

    run_sort(Library(library), keep_folders=False)

    assert folder.exists()
    assert emptyish.exists()


# endregion


# region Duplicates


def _plant(library: Path, relative: str | Path, text: str) -> Path:
    path = library / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _copy(source: Path, library: Path, relative: str | Path) -> Path:
    """A byte-for-byte copy of ``source`` at ``library/relative`` (text round-trips would change line endings)."""

    destination = library / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination


def test_run_sort_duplicate_at_destination_held_in_inbox(tmp_path: Path) -> None:
    library = _library(tmp_path)
    note = library / "_sorting" / _PHOENIX_NOTE
    _copy(note, library, _PHOENIX_DESTINATION)  # the same note, filed earlier

    report = run_sort(Library(library))

    (duplicate,) = report.duplicates
    assert duplicate.unit.source_path == note
    assert duplicate.reason == (
        f"identical to Project Phoenix/02 Architecture/{_PHOENIX_NOTE}, already filed where this would go"
    )
    assert note.exists()  # never moved or deleted
    assert report.filed == []
    assert [unit.source_path.name for unit, _ in report.needs_review] == [_SOLAR_NOTE]  # listed once, here only
    assert report.job is None


def test_run_sort_duplicate_is_still_classified(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _copy(library / "_sorting" / _PHOENIX_NOTE, library, _RESEARCH_DIR / "older.md")

    report = run_sort(Library(library))

    (duplicate,) = report.duplicates
    assert (duplicate.classification.group.name, duplicate.classification.category.name) == (
        "Project Phoenix",
        "02 Architecture",
    )
    assert duplicate.reason == (
        "identical to Project Phoenix/03 Research/older.md; this would be filed in Project Phoenix/02 Architecture"
    )


def test_run_sort_duplicate_under_another_name_held(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _copy(library / "_sorting" / _PHOENIX_NOTE, library, _ARCHITECTURE_DIR / "renamed.md")

    report = run_sort(Library(library))

    (duplicate,) = report.duplicates
    assert (
        duplicate.reason
        == "identical to Project Phoenix/02 Architecture/renamed.md, in the folder this would be filed to"
    )
    assert not (library / _PHOENIX_DESTINATION).exists()


def test_run_sort_unclassifiable_duplicate_listed_once_as_duplicate(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _copy(library / "_sorting" / _SOLAR_NOTE, library, _RESEARCH_DIR / "solar.md")

    report = run_sort(Library(library))

    (duplicate,) = report.duplicates
    assert duplicate.unit.source_path.name == _SOLAR_NOTE
    assert duplicate.reason == "identical to Project Phoenix/03 Research/solar.md; could not be classified"
    assert _SOLAR_NOTE not in [unit.source_path.name for unit, _ in report.needs_review]


def test_run_sort_identical_inbox_files_file_first_hold_second(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _plant(library, "_sorting/a-copy.md", _ARCHITECTURE_TEXT)
    _plant(library, "_sorting/b-copy.md", _ARCHITECTURE_TEXT)

    report = run_sort(Library(library))

    assert "a-copy.md" in [unit.source_path.name for unit, _ in report.filed]
    (duplicate,) = report.duplicates
    assert duplicate.unit.source_path.name == "b-copy.md"
    assert (
        duplicate.reason == "identical to 'a-copy.md', which is being filed this run to Project Phoenix/02 Architecture"
    )
    assert (library / "_sorting" / "b-copy.md").exists()
    assert (library / _ARCHITECTURE_DIR / "a-copy.md").exists()


def test_run_sort_held_duplicate_does_not_claim_destination(tmp_path: Path) -> None:
    library = _library(tmp_path)
    lib = Library(library)
    lib.config.naming_rules.rules = {r"^draft-\d+": "final"}  # both drafts would become final.md
    _plant(library, _RESEARCH_DIR / "old.md", _ARCHITECTURE_TEXT)
    _plant(library, "_sorting/draft-1.md", _ARCHITECTURE_TEXT)  # a copy of old.md, so held
    _plant(library, "_sorting/draft-2.md", _ARCHITECTURE_TEXT + " Revised.")

    report = run_sort(lib)

    assert [d.unit.source_path.name for d in report.duplicates] == ["draft-1.md"]
    assert "draft-2.md" in [unit.source_path.name for unit, _ in report.filed]
    assert (library / _ARCHITECTURE_DIR / "final.md").read_text(encoding="utf-8").endswith("Revised.")


def test_run_sort_same_name_different_content_is_collision_not_duplicate(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _plant(library, _PHOENIX_DESTINATION, "A different document that happens to share the name.")

    report = run_sort(Library(library))

    assert report.duplicates == []
    assert _PHOENIX_NOTE in [unit.source_path.name for unit, _ in report.needs_review]


def test_run_sort_same_size_different_content_files_normally(tmp_path: Path) -> None:
    library = _library(tmp_path)
    note = library / "_sorting" / _PHOENIX_NOTE
    size = len(note.read_bytes())
    _plant(library, _RESEARCH_DIR / "lookalike.md", "z" * size)

    report = run_sort(Library(library))

    assert report.duplicates == []
    assert (library / _PHOENIX_DESTINATION).exists()


def test_run_sort_duplicates_already_in_library_not_reported(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _plant(library, _ARCHITECTURE_DIR / "reference.md", "A reference document kept in two projects.")
    _plant(library, _RESEARCH_DIR / "reference.md", "A reference document kept in two projects.")

    report = run_sort(Library(library))

    assert report.duplicates == []
    assert [unit.source_path.name for unit, _ in report.filed] == [_PHOENIX_NOTE]


def test_run_sort_duplicate_does_not_stop_rest_and_rollback_restores(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _copy(library / "_sorting" / _SOLAR_NOTE, library, _RESEARCH_DIR / "solar.md")
    before = _snapshot(library)

    report = run_sort(Library(library))

    assert [unit.source_path.name for unit, _ in report.filed] == [_PHOENIX_NOTE]  # filed beside the held duplicate
    assert report.job is not None
    rollback_job(Library(library), report.job.job_id)
    assert _snapshot(library) == before


def test_run_sort_folders_off_duplicate_inside_folder_held_and_folder_stays(tmp_path: Path) -> None:
    library = _library(tmp_path, with_pack=True)
    _copy(library / "_sorting" / _PACK / "research-summary.md", library, _RESEARCH_DIR / "already-filed.md")

    report = run_sort(Library(library), keep_folders=False)

    assert [d.unit.source_path.name for d in report.duplicates] == ["research-summary.md"]
    assert (library / "_sorting" / _PACK / "research-summary.md").exists()
    assert (library / _ARCHITECTURE_DIR / "architecture-decision-log.md").exists()
    ((folder, reason),) = report.folders_kept
    assert folder == library / "_sorting" / _PACK
    assert reason == "it still holds research-summary.md (duplicate)"


def test_run_sort_folder_kept_whole_not_checked_for_duplicates(tmp_path: Path) -> None:
    library = _library(tmp_path, with_pack=True)
    for name in _PACK_FILES:
        _copy(library / "_sorting" / _PACK / name, library, _RESEARCH_DIR / f"copy-of-{name}")

    report = run_sort(Library(library), keep_folders=True)

    assert report.duplicates == []
    assert (library / _ARCHITECTURE_DIR / _PACK).is_dir()  # filed whole, as before


# endregion
