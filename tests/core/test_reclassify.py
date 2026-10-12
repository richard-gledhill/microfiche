"""Tests for reclassification (re-reviewing already-filed documents)."""

import logging
import shutil
from collections import Counter
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

# region Test helpers


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


# endregion


# region Planning proposals


def test_run_reclassify_proposals_describe_each_action(tmp_path: Path) -> None:
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


def test_run_reclassify_dry_run_changes_nothing(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library, f"{_RESEARCH}/misfiled.md", _ARCHITECTURE_TEXT)
    before = _snapshot(library)

    run_reclassify(Library(library))

    assert _snapshot(library) == before
    assert not (library / MICROFICHE_DIRNAME / "rollback").exists()
    assert not Ledger(library / MICROFICHE_DIRNAME).path.exists()


def test_run_reclassify_keeps_document_in_category_subfolder(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library, f"{_ARCHITECTURE}/diagrams/nested.md", _ARCHITECTURE_TEXT)

    proposals = _by_name(run_reclassify(Library(library)))

    assert proposals["nested.md"].action == "keep"


def test_run_reclassify_taken_destination_conflict(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library, f"{_RESEARCH}/dup.md", _ARCHITECTURE_TEXT)
    _write(library, f"{_ARCHITECTURE}/dup.md", _ARCHITECTURE_TEXT)

    proposals = _named(run_reclassify(Library(library)), "dup.md")

    assert sorted(p.action for p in proposals) == ["conflict", "keep"]
    conflict = next(p for p in proposals if p.action == "conflict")
    assert conflict.destination == library / _ARCHITECTURE / "dup.md"


def test_run_reclassify_same_destination_moves_only_one(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library, f"{_REQUIREMENTS}/same.md", _ARCHITECTURE_TEXT)
    _write(library, f"{_RESEARCH}/same.md", _ARCHITECTURE_TEXT)

    proposals = _named(run_reclassify(Library(library)), "same.md")

    assert [p.action for p in proposals] == ["move", "conflict"]  # documents are visited in sorted path order


# endregion


# region Applying proposals


def test_apply_reclassification_moves_only_move_proposals(tmp_path: Path) -> None:
    library = _library(tmp_path)
    lib = Library(library)
    _write(library, f"{_RESEARCH}/misfiled.md", _ARCHITECTURE_TEXT)
    _write(library, f"{_ARCHITECTURE}/in-place.md", _ARCHITECTURE_TEXT)
    _write(library, f"{_RESEARCH}/unclear.md", _UNCLEAR_TEXT)
    proposals = run_reclassify(lib)

    job = apply_reclassification(lib, proposals).job

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


def test_apply_reclassification_nothing_to_move_writes_nothing(tmp_path: Path) -> None:
    library = _library(tmp_path)
    lib = Library(library)
    _write(library, f"{_ARCHITECTURE}/in-place.md", _ARCHITECTURE_TEXT)
    before = _snapshot(library)

    job = apply_reclassification(lib, run_reclassify(lib)).job

    assert job is None
    assert _snapshot(library) == before
    assert not (library / MICROFICHE_DIRNAME / "rollback").exists()


def test_apply_reclassification_rollback_restores_library(tmp_path: Path) -> None:
    library = _library(tmp_path)
    lib = Library(library)
    _write(library, f"{_RESEARCH}/misfiled.md", _ARCHITECTURE_TEXT)
    before = _snapshot(library)
    job = apply_reclassification(lib, run_reclassify(lib)).job
    assert job is not None
    assert _snapshot(library) != before

    rollback_job(Library(library), job.job_id)

    assert _snapshot(library) == before
    assert Ledger(library / MICROFICHE_DIRNAME).current() == []


def test_run_reclassify_naming_rules_apply_to_destination(tmp_path: Path) -> None:
    library = _library(tmp_path)
    lib = Library(library)
    lib.config.naming_rules.rules = {"^misfiled": "refiled"}
    _write(library, f"{_RESEARCH}/misfiled.md", _ARCHITECTURE_TEXT)
    proposals = run_reclassify(lib)

    assert _by_name(proposals)["misfiled.md"].destination == library / _ARCHITECTURE / "refiled.md"
    apply_reclassification(lib, proposals)

    assert (library / _ARCHITECTURE / "refiled.md").exists()


def test_apply_reclassification_destination_taken_after_preview_fails_that_document_only(
    tmp_path: Path,
) -> None:
    library = _library(tmp_path)
    lib = Library(library)
    _write(library, f"{_RESEARCH}/a-first.md", _ARCHITECTURE_TEXT)
    _write(library, f"{_RESEARCH}/b-second.md", _ARCHITECTURE_TEXT + " Second.")
    before = _snapshot(library)
    proposals = run_reclassify(lib)
    blocker = _write(library, f"{_ARCHITECTURE}/b-second.md", "appeared after the preview")

    result = apply_reclassification(lib, proposals)

    assert [failure.unit.source_path.name for failure in result.failed] == ["b-second.md"]
    assert (library / _ARCHITECTURE / "a-first.md").exists()
    assert (library / _RESEARCH / "b-second.md").exists()  # stays where it was
    assert result.job is not None
    blocker.unlink()
    rollback_job(Library(library), result.job.job_id)
    assert _snapshot(library) == before


# endregion


# region Scope and exclusions


def test_run_reclassify_skips_config_and_logs_folders(tmp_path: Path) -> None:
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


def test_run_reclassify_scope_limits_documents(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _write(library, f"{_RESEARCH}/in-scope.md", _ARCHITECTURE_TEXT)
    _write(library, f"{_REQUIREMENTS}/out-of-scope.md", _ARCHITECTURE_TEXT)

    proposals = run_reclassify(Library(library), scope=library / _RESEARCH)

    assert [p.current_path.name for p in proposals] == ["in-scope.md"]


def test_run_reclassify_cwd_relative_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    _write(library, f"{_ARCHITECTURE}/in-place.md", _ARCHITECTURE_TEXT)
    monkeypatch.chdir(tmp_path)

    proposals = run_reclassify(Library(library), scope=Path("library") / _ARCHITECTURE)

    assert [(p.current_path.name, p.action) for p in proposals] == [("in-place.md", "keep")]


def test_run_reclassify_outside_scope_refused(tmp_path: Path) -> None:
    library = _library(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    with pytest.raises(ScopeOutsideLibraryError):
        run_reclassify(Library(library), scope=outside)


# endregion


# region Confidence threshold


def test_run_reclassify_threshold_decides_hint_match_move(tmp_path: Path) -> None:
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


# endregion


# region Unreadable files


def test_run_reclassify_unreadable_file_left_for_review(tmp_path: Path) -> None:
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


# endregion


# region Logging


def test_run_reclassify_logs_each_action_and_a_summary(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    library = Library(_library(tmp_path))
    caplog.set_level(logging.DEBUG, logger="core")

    proposals = run_reclassify(library)

    counts = Counter(proposal.action for proposal in proposals)
    assert proposals
    assert (
        f"reclassify: checked {len(proposals)} document(s): {counts['move']} move, {counts['keep']} keep, "
        f"{counts['review']} review, {counts['conflict']} conflict"
    ) in caplog.messages
    for proposal in proposals:
        assert f"{library.relative(proposal.current_path)}: {proposal.action}" in caplog.messages


# endregion


# region Progress


def test_run_reclassify_reports_progress_from_zero_to_the_total(tmp_path: Path) -> None:
    calls: list[tuple[int, int]] = []

    proposals = run_reclassify(Library(_library(tmp_path)), progress=lambda done, total: calls.append((done, total)))

    total = len(proposals)
    assert total > 0
    assert calls == [(done, total) for done in range(total + 1)]


# endregion
