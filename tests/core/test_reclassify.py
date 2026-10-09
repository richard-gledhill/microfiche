"""Tests for reclassification (re-reviewing already-filed documents)."""

import shutil
from pathlib import Path

import pytest
from core.config import MICROFICHE_DIRNAME, load_config
from core.filer import AUDIT_LOG_FILENAME, rollback_job
from core.ledger import Ledger
from core.library.library import Library, ScopeOutsideLibraryError
from core.reclassify import (
    ReclassifyProposal,
    apply_reclassification,
    run_reclassify,
)
from core.utils.hashing import file_hash

_REPO_CONFIG_DIR = Path(__file__).resolve().parents[2] / "microfiche"
_MOCK_LIBRARY = Path(__file__).resolve().parents[1] / "mock_library"

# Names the group and the "architecture" category, so the rules engine files it confidently.
_ARCHITECTURE_TEXT = "Project Phoenix architecture decisions."
_UNCLEAR_TEXT = "Nothing recognisable in here."

_RESEARCH = "Project Phoenix/03 Research"
_ARCHITECTURE = "Project Phoenix/02 Architecture"
_REQUIREMENTS = "Project Phoenix/01 Requirements"


def _library(tmp_path: Path) -> Path:
    library = tmp_path / "library"
    shutil.copytree(_MOCK_LIBRARY, library)
    return library


def _write(library: Path, relative_path: str, text: str) -> Path:
    path = library / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _snapshot(library: Path) -> dict[str, str]:
    """Library-relative path -> hash for every file, ignoring microfiche's own state."""

    state_dir = library / MICROFICHE_DIRNAME
    return {
        path.relative_to(library).as_posix(): file_hash(path)
        for path in sorted(library.rglob("*"))
        if path.is_file() and not path.is_relative_to(state_dir)
    }


def _by_name(proposals: list[ReclassifyProposal]) -> dict[str, ReclassifyProposal]:
    return {proposal.current_path.name: proposal for proposal in proposals}


def _named(proposals: list[ReclassifyProposal], name: str) -> list[ReclassifyProposal]:
    return [proposal for proposal in proposals if proposal.current_path.name == name]


def test_proposals_say_what_applying_would_do_with_each_document(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library, f"{_RESEARCH}/misfiled.md", _ARCHITECTURE_TEXT)
    _write(library, f"{_ARCHITECTURE}/in-place.md", _ARCHITECTURE_TEXT)
    _write(library, f"{_RESEARCH}/unclear.md", _UNCLEAR_TEXT)

    proposals = _by_name(run_reclassify(Library(library)))

    misfiled = proposals["misfiled.md"]
    assert misfiled.action == "move"
    assert misfiled.destination == library / _ARCHITECTURE / "misfiled.md"
    assert (misfiled.proposed_group, misfiled.proposed_category) == ("Project Phoenix", "02 Architecture")
    assert proposals["in-place.md"].action == "keep"
    assert proposals["in-place.md"].destination is None
    assert proposals["unclear.md"].action == "review"
    assert proposals["unclear.md"].destination is None


def test_a_dry_run_changes_nothing_and_writes_no_state(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library, f"{_RESEARCH}/misfiled.md", _ARCHITECTURE_TEXT)
    before = _snapshot(library)

    run_reclassify(Library(library))

    assert _snapshot(library) == before
    assert not (library / MICROFICHE_DIRNAME / "rollback").exists()
    assert not Ledger(library / MICROFICHE_DIRNAME).path.exists()


def test_a_document_already_under_its_category_folder_is_kept_even_in_a_subfolder(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library, f"{_ARCHITECTURE}/diagrams/nested.md", _ARCHITECTURE_TEXT)

    proposals = _by_name(run_reclassify(Library(library)))

    assert proposals["nested.md"].action == "keep"


def test_a_destination_that_is_already_taken_is_a_conflict_not_a_move(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library, f"{_RESEARCH}/dup.md", _ARCHITECTURE_TEXT)
    _write(library, f"{_ARCHITECTURE}/dup.md", _ARCHITECTURE_TEXT)

    proposals = _named(run_reclassify(Library(library)), "dup.md")

    assert sorted(p.action for p in proposals) == ["conflict", "keep"]
    conflict = next(p for p in proposals if p.action == "conflict")
    assert conflict.destination == library / _ARCHITECTURE / "dup.md"


def test_two_documents_headed_for_the_same_destination_only_move_one(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library, f"{_REQUIREMENTS}/same.md", _ARCHITECTURE_TEXT)
    _write(library, f"{_RESEARCH}/same.md", _ARCHITECTURE_TEXT)

    proposals = _named(run_reclassify(Library(library)), "same.md")

    assert [p.action for p in proposals] == ["move", "conflict"]  # documents are visited in sorted path order


def test_apply_moves_only_the_move_proposals_as_one_recorded_job(tmp_path: Path) -> None:
    library = _library(tmp_path)
    lib = Library(library)
    _write(library, f"{_RESEARCH}/misfiled.md", _ARCHITECTURE_TEXT)
    _write(library, f"{_ARCHITECTURE}/in-place.md", _ARCHITECTURE_TEXT)
    _write(library, f"{_RESEARCH}/unclear.md", _UNCLEAR_TEXT)
    proposals = run_reclassify(lib)

    job = apply_reclassification(lib, proposals)

    assert job is not None
    assert not (library / _RESEARCH / "misfiled.md").exists()
    assert (library / _ARCHITECTURE / "misfiled.md").read_text(encoding="utf-8") == _ARCHITECTURE_TEXT
    assert (library / _ARCHITECTURE / "in-place.md").exists()
    assert (library / _RESEARCH / "unclear.md").exists()
    assert [move.new_path for move in job.moves] == [library / _ARCHITECTURE / "misfiled.md"]
    (record,) = Ledger(library / MICROFICHE_DIRNAME).current()
    assert record.job_id == job.job_id
    assert record.original_path == f"{_RESEARCH}/misfiled.md"
    assert record.path == f"{_ARCHITECTURE}/misfiled.md"
    audit = (library / MICROFICHE_DIRNAME / AUDIT_LOG_FILENAME).read_text(encoding="utf-8")
    assert f"move {_RESEARCH}/misfiled.md -> {_ARCHITECTURE}/misfiled.md" in audit


def test_apply_with_nothing_to_move_writes_nothing(tmp_path: Path) -> None:
    library = _library(tmp_path)
    lib = Library(library)
    _write(library, f"{_ARCHITECTURE}/in-place.md", _ARCHITECTURE_TEXT)
    before = _snapshot(library)

    job = apply_reclassification(lib, run_reclassify(lib))

    assert job is None
    assert _snapshot(library) == before
    assert not (library / MICROFICHE_DIRNAME / "rollback").exists()


def test_a_reclassification_can_be_rolled_back_to_the_exact_prior_library(tmp_path: Path) -> None:
    library = _library(tmp_path)
    lib = Library(library)
    _write(library, f"{_RESEARCH}/misfiled.md", _ARCHITECTURE_TEXT)
    before = _snapshot(library)
    job = apply_reclassification(lib, run_reclassify(lib))
    assert job is not None
    assert _snapshot(library) != before

    rollback_job(Library(library), job.job_id)

    assert _snapshot(library) == before
    assert Ledger(library / MICROFICHE_DIRNAME).current() == []


def test_naming_rules_apply_to_the_proposed_destination_and_the_move(tmp_path: Path) -> None:
    library = _library(tmp_path)
    lib = Library(library)
    lib.config.naming_rules.rules = {"^misfiled": "refiled"}
    _write(library, f"{_RESEARCH}/misfiled.md", _ARCHITECTURE_TEXT)
    proposals = run_reclassify(lib)

    assert _by_name(proposals)["misfiled.md"].destination == library / _ARCHITECTURE / "refiled.md"
    apply_reclassification(lib, proposals)

    assert (library / _ARCHITECTURE / "refiled.md").exists()


def test_a_destination_taken_after_planning_stops_the_apply_but_keeps_earlier_moves_rollbackable(
    tmp_path: Path,
) -> None:
    library = _library(tmp_path)
    lib = Library(library)
    _write(library, f"{_RESEARCH}/a-first.md", _ARCHITECTURE_TEXT)
    _write(library, f"{_RESEARCH}/b-second.md", _ARCHITECTURE_TEXT)
    before = _snapshot(library)
    proposals = run_reclassify(lib)
    blocker = _write(library, f"{_ARCHITECTURE}/b-second.md", "appeared after the preview")

    with pytest.raises(FileExistsError):
        apply_reclassification(lib, proposals)

    assert (library / _ARCHITECTURE / "a-first.md").exists()
    assert (library / _RESEARCH / "b-second.md").exists()
    (job_file,) = (library / MICROFICHE_DIRNAME / "rollback").glob("job_*.json")
    blocker.unlink()
    rollback_job(Library(library), job_file.stem.removeprefix("job_"))
    assert _snapshot(library) == before


def test_reclassify_never_scans_the_library_s_own_config_or_logs_folders(tmp_path: Path) -> None:
    """Regression test: .microfiche/ is an operational folder, not sortable content.

    Uses the actual shipped default exclusions (microfiche-config.toml [exclusions], not a
    synthetic one, so this catches a regression in the defaults themselves.
    """

    (tmp_path / "Project Phoenix" / "01 Requirements").mkdir(parents=True)
    config_dir = tmp_path / ".microfiche"
    config_dir.mkdir()
    (config_dir / "README.md").write_text("Not a project document.", encoding="utf-8")
    (tmp_path / ".logs").mkdir()
    (tmp_path / ".logs" / "notes.md").write_text("Not a project document either.", encoding="utf-8")

    config = load_config(_REPO_CONFIG_DIR)
    proposals = run_reclassify(Library(tmp_path, config=config))

    assert proposals == []


def test_scope_limits_which_documents_are_considered(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library, f"{_RESEARCH}/in-scope.md", _ARCHITECTURE_TEXT)
    _write(library, f"{_REQUIREMENTS}/out-of-scope.md", _ARCHITECTURE_TEXT)

    proposals = run_reclassify(Library(library), scope=library / _RESEARCH)

    assert [p.current_path.name for p in proposals] == ["in-scope.md"]


def test_a_relative_scope_is_understood_relative_to_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _library(tmp_path)
    _write(library, f"{_ARCHITECTURE}/in-place.md", _ARCHITECTURE_TEXT)
    monkeypatch.chdir(tmp_path)

    proposals = run_reclassify(Library(library), scope=Path("library") / _ARCHITECTURE)

    assert [(p.current_path.name, p.action) for p in proposals] == [("in-place.md", "keep")]


def test_a_scope_outside_the_library_is_refused(tmp_path: Path) -> None:
    library = _library(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    with pytest.raises(ScopeOutsideLibraryError):
        run_reclassify(Library(library), scope=outside)


def test_the_libraries_confidence_threshold_decides_whether_a_hint_match_is_moved(tmp_path: Path) -> None:
    """A keyword hint scores 0.75: it is moved at the default threshold, held if the library raises it."""

    library = _library(tmp_path)
    _write(library, f"{_RESEARCH}/backlog.md", "Project Phoenix user story backlog.")  # keyword hint: 0.75
    lib = Library(library)

    at_default = _by_name(run_reclassify(lib))["backlog.md"]
    lib.config.classification.confidence_threshold = 0.8
    raised = _by_name(run_reclassify(lib))["backlog.md"]

    assert at_default.action == "move"
    assert at_default.destination == library / _REQUIREMENTS / "backlog.md"
    assert raised.action == "review"


def test_an_unreadable_file_is_left_for_review_and_does_not_stop_the_rest(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library, f"{_RESEARCH}/broken.docx", "this is not a zip file")
    _write(library, f"{_RESEARCH}/misfiled.md", _ARCHITECTURE_TEXT)
    lib = Library(library)

    proposals = _by_name(run_reclassify(lib))

    assert proposals["broken.docx"].action == "review"
    assert proposals["broken.docx"].classification.classified_by == "unreadable"
    assert proposals["broken.docx"].classification.category.reason.startswith("Could not read 'broken.docx':")
    assert proposals["misfiled.md"].action == "move"

    apply_reclassification(lib, list(proposals.values()))

    assert (library / _RESEARCH / "broken.docx").exists()
    assert (library / _ARCHITECTURE / "misfiled.md").exists()
