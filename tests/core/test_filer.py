"""Tests for filing a batch of classified units and rolling the job back."""

import logging
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from conftest import LinkMaker
from microfiche.core.filer import (
    AUDIT_LOG_FILENAME,
    DestinationClaims,
    JobAlreadyRolledBackError,
    JobMoveMissingError,
    JobNotFoundError,
    NoJobToRollBackError,
    UnresolvedClassificationError,
    file_batch,
    latest_job,
    load_job,
    rollback_job,
    save_job,
)
from microfiche.core.ledger import Ledger
from microfiche.core.library.library import Library
from microfiche.core.models.classification import CategoryMatch, ClassificationResult, GroupMatch
from microfiche.core.models.document import Document
from microfiche.core.models.job import Job
from microfiche.core.models.unit import SortableUnit
from microfiche.core.utils.filesystem import safe_move
from microfiche.core.utils.hashing import file_hash, unit_hash

# region Test helpers


GROUP = "Project Phoenix"
REQUIREMENTS = "01 Requirements"
ARCHITECTURE = "02 Architecture"


def _library(tmp_path: Path) -> Path:
    library = tmp_path / "library"
    (library / GROUP / REQUIREMENTS).mkdir(parents=True)
    (library / GROUP / ARCHITECTURE).mkdir(parents=True)
    (library / "_sorting").mkdir()
    return library


def _file_unit(library: Path, name: str, text: str = "some content") -> SortableUnit:
    path = library / "_sorting" / name
    path.write_text(text, encoding="utf-8")
    document = Document(file_path=path, file_name=name, extension=path.suffix, content=text)
    return SortableUnit(source_path=path, kind="file", documents=[document])


def _folder_unit(library: Path, name: str) -> SortableUnit:
    folder = library / "_sorting" / name
    (folder / "nested").mkdir(parents=True)
    (folder / "one.md").write_text("first", encoding="utf-8")
    (folder / "nested" / "two.md").write_text("second", encoding="utf-8")
    document = Document(file_path=folder / "one.md", file_name="one.md", extension=".md", content="first")
    return SortableUnit(source_path=folder, kind="folder", documents=[document])


def _unit_from_folder(library: Path, relative: str, origin: str = "pack", text: str = "some content") -> SortableUnit:
    """A file unit taken out of the inbox folder ``origin``; ``relative`` is its path inside the inbox."""

    path = library / "_sorting" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    document = Document(file_path=path, file_name=path.name, extension=path.suffix, content=text)
    return SortableUnit(
        source_path=path, kind="file", documents=[document], origin_folder=library / "_sorting" / origin
    )


def _classified(category: str | None = REQUIREMENTS, group: str | None = GROUP) -> ClassificationResult:
    return ClassificationResult(
        group=GroupMatch(name=group, confidence=1.0, reason="group reason"),
        category=CategoryMatch(name=category, confidence=0.9, reason="category reason"),
        overall_confidence=0.9,
        classified_by="rules_engine",
        confident=True,
    )


def _snapshot(library: Path) -> dict[str, str]:
    """Library-relative path -> hash for every file, ignoring microfiche's own state folder."""

    return {
        path.relative_to(library).as_posix(): file_hash(path)
        for path in sorted(library.rglob("*"))
        if path.is_file() and ".microfiche" not in path.relative_to(library).parts
    }


# endregion


# region Public API


# region file_batch


def test_file_batch_moves_units_to_group_category(tmp_path: Path) -> None:
    library = _library(tmp_path)
    requirements = _file_unit(library, "reqs.md")
    design = _file_unit(library, "design.md")

    job = file_batch(Library(library), [(requirements, _classified()), (design, _classified(ARCHITECTURE))]).job

    assert job is not None
    assert (library / GROUP / REQUIREMENTS / "reqs.md").read_text(encoding="utf-8") == "some content"
    assert (library / GROUP / ARCHITECTURE / "design.md").exists()
    assert not (library / "_sorting" / "reqs.md").exists()
    assert [move.action for move in job.moves] == ["move", "move"]


def test_file_batch_writes_no_sidecar_files(tmp_path: Path) -> None:
    library = _library(tmp_path)

    file_batch(Library(library), [(_file_unit(library, "reqs.md"), _classified())])

    assert list(library.rglob("*.metadata.json")) == []


def test_file_batch_empty_writes_nothing(tmp_path: Path) -> None:
    library = _library(tmp_path)

    assert file_batch(Library(library), []).job is None
    assert not (library / ".microfiche").exists()


def test_file_batch_applies_naming_rules(tmp_path: Path) -> None:
    library = _library(tmp_path)

    lib = Library(library)
    lib.config.naming_rules.rules = {"^draft_": "final_"}

    file_batch(lib, [(_file_unit(library, "draft_reqs.md"), _classified())])

    assert (library / GROUP / REQUIREMENTS / "final_reqs.md").exists()


def test_file_batch_saves_loadable_job(tmp_path: Path) -> None:
    library = _library(tmp_path)

    job = file_batch(Library(library), [(_file_unit(library, "reqs.md"), _classified())]).job

    assert job is not None
    loaded = load_job(library / ".microfiche", job.job_id)
    assert loaded == job
    assert loaded.rolled_back_at is None


def test_file_batch_records_what_and_why_in_ledger(tmp_path: Path) -> None:
    library = _library(tmp_path)
    unit = _file_unit(library, "reqs.md", text="hash me")
    expected_hash = file_hash(unit.source_path)

    job = file_batch(Library(library), [(unit, _classified())]).job

    assert job is not None
    (record,) = Ledger(library / ".microfiche").current()
    assert record.event == "filed"
    assert record.job_id == job.job_id
    assert record.path == f"{GROUP}/{REQUIREMENTS}/reqs.md"
    assert record.original_path == "_sorting/reqs.md"
    assert record.content_hash == expected_hash == file_hash(library / record.path)
    assert (record.unit_type, record.group, record.category) == ("file", GROUP, REQUIREMENTS)
    assert (record.group_reason, record.category_reason) == ("group reason", "category reason")
    assert (record.confidence, record.classified_by) == (0.9, "rules_engine")


def test_file_batch_appends_audit_line_per_move(tmp_path: Path) -> None:
    library = _library(tmp_path)

    job = file_batch(
        Library(library), [(_file_unit(library, "a.md"), _classified()), (_file_unit(library, "b.md"), _classified())]
    ).job

    assert job is not None
    lines = (library / ".microfiche" / AUDIT_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(f"job={job.job_id} move _sorting/" in line for line in lines)
    assert lines[0].endswith(f"_sorting/a.md -> {GROUP}/{REQUIREMENTS}/a.md")


def test_file_batch_unresolved_aborts_before_moving(tmp_path: Path) -> None:
    library = _library(tmp_path)
    good = _file_unit(library, "good.md")
    bad = _file_unit(library, "bad.md")

    with pytest.raises(UnresolvedClassificationError):
        file_batch(Library(library), [(good, _classified()), (bad, _classified(category=None))])

    assert good.source_path.exists()
    assert bad.source_path.exists()
    assert not (library / ".microfiche").exists()


def _flat_classified(group: str | None = GROUP) -> ClassificationResult:
    """A classification from a flat library: a group and no category at all."""

    return ClassificationResult(
        group=GroupMatch(name=group, confidence=1.0, reason="group reason"),
        category=None,
        overall_confidence=1.0,
        classified_by="rules_engine",
        confident=True,
    )


def test_file_batch_flat_library_files_straight_into_the_group(tmp_path: Path) -> None:
    library = _library(tmp_path)
    unit = _file_unit(library, "note.md")

    result = file_batch(Library(library), [(unit, _flat_classified())])

    assert (library / GROUP / "note.md").is_file()
    assert not unit.source_path.exists()
    assert result.job is not None
    (record,) = Ledger(library / ".microfiche").read_all()
    assert (record.group, record.category) == (GROUP, None)
    assert record.category_reason is None
    assert record.path == f"{GROUP}/note.md"


def test_file_batch_flat_library_unresolved_group_refused_before_anything_moves(tmp_path: Path) -> None:
    library = _library(tmp_path)
    good = _file_unit(library, "good.md")
    bad = _file_unit(library, "bad.md")

    with pytest.raises(UnresolvedClassificationError):
        file_batch(Library(library), [(good, _flat_classified()), (bad, _flat_classified(group=None))])

    assert good.source_path.exists()
    assert not (library / ".microfiche").exists()


def test_file_batch_folder_filed_whole_hashed_as_manifest(tmp_path: Path) -> None:
    library = _library(tmp_path)
    unit = _folder_unit(library, "bundle")
    expected_hash = unit_hash(unit.source_path)

    file_batch(Library(library), [(unit, _classified())])

    assert (library / GROUP / REQUIREMENTS / "bundle" / "nested" / "two.md").exists()
    (record,) = Ledger(library / ".microfiche").current()
    assert record.unit_type == "folder"
    assert record.content_hash == expected_hash == unit_hash(library / record.path)


def test_file_batch_emptied_origin_folder_removed_and_recorded(tmp_path: Path) -> None:
    library = _library(tmp_path)
    one = _unit_from_folder(library, "pack/one.md")
    two = _unit_from_folder(library, "pack/sub/two.md")

    job = file_batch(Library(library), [(one, _classified()), (two, _classified())]).job

    assert job is not None
    assert not (library / "_sorting" / "pack").exists()
    removed = [event for event in job.moves if event.action == "remove_folder"]
    assert [event.original_path for event in removed] == [
        library / "_sorting" / "pack" / "sub",
        library / "_sorting" / "pack",
    ]
    assert all(event.new_path is None for event in removed)
    assert load_job(library / ".microfiche", job.job_id) == job  # the removals are in the saved job
    lines = (library / ".microfiche" / AUDIT_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    assert [line.split(" ", 3)[2:] for line in lines if "remove_folder" in line] == [
        ["remove_folder", "_sorting/pack/sub -> -"],
        ["remove_folder", "_sorting/pack -> -"],
    ]
    assert len(Ledger(library / ".microfiche").current()) == 2  # a folder removal is not a filed unit


@pytest.mark.parametrize("maker", ["make_symlink", "make_junction"])
def test_file_batch_inbox_folder_holding_a_link_is_kept_and_the_link_target_untouched(
    tmp_path: Path, request: pytest.FixtureRequest, maker: str
) -> None:
    make_link: LinkMaker = request.getfixturevalue(maker)
    library = _library(tmp_path)
    unit = _unit_from_folder(library, "pack/one.md")
    outside = tmp_path / "elsewhere"
    (outside / "empty" / "deeper").mkdir(parents=True)
    make_link(library / "_sorting" / "pack" / "link", outside)

    job = file_batch(Library(library), [(unit, _classified())]).job

    assert job is not None
    assert (library / GROUP / REQUIREMENTS / "one.md").exists()
    assert (outside / "empty" / "deeper").is_dir()  # nothing behind the link is removed
    assert (library / "_sorting" / "pack" / "link").exists()  # and the link, which is something in the folder, stays
    assert [event.action for event in job.moves] == ["move"]


def test_file_batch_folder_that_cannot_be_removed_left_and_unrecorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _library(tmp_path)
    unit = _unit_from_folder(library, "pack/one.md")

    def locked(self: Path, *args: object) -> None:
        raise PermissionError(self)

    monkeypatch.setattr(Path, "rmdir", locked)

    job = file_batch(Library(library), [(unit, _classified())]).job

    assert job is not None
    assert (library / "_sorting" / "pack").is_dir()  # the move still happened, the folder just stays
    assert (library / GROUP / REQUIREMENTS / "one.md").exists()
    assert [event.action for event in job.moves] == ["move"]  # a removal that did not happen is not recorded


def test_file_batch_origin_folder_with_leftover_file_kept(tmp_path: Path) -> None:
    library = _library(tmp_path)
    unit = _unit_from_folder(library, "pack/one.md")
    (library / "_sorting" / "pack" / "photo.png").write_bytes(b"x")

    job = file_batch(Library(library), [(unit, _classified())]).job

    assert job is not None
    assert (library / "_sorting" / "pack" / "photo.png").exists()
    assert [event.action for event in job.moves] == ["move"]


def test_file_batch_origin_folder_left_when_a_sibling_unit_not_filed(tmp_path: Path) -> None:
    library = _library(tmp_path)
    filed = _unit_from_folder(library, "pack/one.md")
    _unit_from_folder(library, "pack/two.md")  # in the folder, but not part of this batch

    file_batch(Library(library), [(filed, _classified())])

    assert (library / "_sorting" / "pack" / "two.md").exists()


def test_file_batch_unit_without_origin_folder_removes_nothing(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / "_sorting" / "elsewhere").mkdir()  # an empty folder that no unit came from

    job = file_batch(Library(library), [(_file_unit(library, "loose.md"), _classified())]).job

    assert job is not None
    assert (library / "_sorting" / "elsewhere").is_dir()
    assert [event.action for event in job.moves] == ["move"]


def test_file_batch_destination_taken_midway_fails_that_unit_only(tmp_path: Path) -> None:
    # The destination appears after the batch was planned, so it is not caught earlier: the one unit fails.
    library = _library(tmp_path)
    first = _file_unit(library, "first.md")
    second = _file_unit(library, "second.md")
    third = _file_unit(library, "third.md")
    (library / GROUP / ARCHITECTURE / "second.md").write_text("already here", encoding="utf-8")
    before = _snapshot(library)

    result = file_batch(
        Library(library), [(first, _classified()), (second, _classified(ARCHITECTURE)), (third, _classified())]
    )

    assert [failure.unit for failure in result.failed] == [second]
    assert result.failed[0].reason == "something took its place at the destination while sorting"
    assert (library / GROUP / REQUIREMENTS / "first.md").exists()
    assert (library / GROUP / REQUIREMENTS / "third.md").exists()  # the rest of the batch carried on
    assert second.source_path.exists()
    assert (library / GROUP / ARCHITECTURE / "second.md").read_text(encoding="utf-8") == "already here"
    assert result.job is not None
    assert [move.original_path.name for move in result.job.moves] == ["first.md", "third.md"]
    assert sorted(r.path for r in Ledger(library / ".microfiche").current()) == [
        f"{GROUP}/{REQUIREMENTS}/first.md",
        f"{GROUP}/{REQUIREMENTS}/third.md",
    ]

    rollback_job(Library(library), result.job.job_id)

    assert _snapshot(library) == before


# endregion


# region file_batch failures


def _in_use(winerror: int) -> PermissionError:
    """The error Windows raises for a file another program has open (errno 13, plus a Windows error code).

    The fourth argument becomes ``.winerror`` on Windows and is ignored elsewhere.
    """

    return PermissionError(
        13, "The process cannot access the file because it is being used by another process", None, winerror
    )


_WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="the Windows error code only exists on Windows")


def test_file_batch_open_file_stays_put_unrecorded_and_batch_continues(
    tmp_path: Path, hold_open: Callable[[Path], None]
) -> None:
    library = _library(tmp_path)
    locked = _file_unit(library, "locked.docx")
    free = _file_unit(library, "free.md")
    hold_open(locked.source_path)
    before = _snapshot(library)

    result = file_batch(Library(library), [(locked, _classified()), (free, _classified())])

    (failure,) = result.failed
    assert failure.unit is locked
    assert failure.reason == "it is open in another program; close it and sort again"
    assert locked.source_path.exists()
    assert not (library / GROUP / REQUIREMENTS / "locked.docx").exists()  # no stray copy
    assert (library / GROUP / REQUIREMENTS / "free.md").exists()
    assert result.job is not None
    assert [move.original_path.name for move in result.job.moves] == ["free.md"]
    assert [r.original_path for r in Ledger(library / ".microfiche").read_all()] == ["_sorting/free.md"]
    assert "locked.docx" not in (library / ".microfiche" / AUDIT_LOG_FILENAME).read_text(encoding="utf-8")
    rollback_job(Library(library), result.job.job_id)
    assert _snapshot(library) == before


def test_file_batch_every_move_fails_writes_nothing(tmp_path: Path, hold_open: Callable[[Path], None]) -> None:
    library = _library(tmp_path)
    locked = _file_unit(library, "locked.docx")
    hold_open(locked.source_path)

    result = file_batch(Library(library), [(locked, _classified())])

    assert result.job is None
    assert len(result.failed) == 1
    state_dir = library / ".microfiche"
    assert not (state_dir / "rollback").exists()
    assert not (state_dir / AUDIT_LOG_FILENAME).exists()
    assert not Ledger(state_dir).path.exists()


def test_file_batch_folder_with_open_file_stays_whole_and_unrecorded(
    tmp_path: Path, hold_open: Callable[[Path], None]
) -> None:
    library = _library(tmp_path)
    unit = _folder_unit(library, "bundle")
    hold_open(library / "_sorting" / "bundle" / "one.md")

    result = file_batch(Library(library), [(unit, _classified())])

    assert result.job is None
    assert sorted(path.name for path in (library / "_sorting" / "bundle").rglob("*.md")) == ["one.md", "two.md"]
    assert not (library / GROUP / REQUIREMENTS / "bundle").exists()  # no partial copy of the folder


def test_file_batch_failed_unit_keeps_its_inbox_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    moved = _unit_from_folder(library, "pack/one.md")
    stuck = _unit_from_folder(library, "pack/two.md")
    real_move = safe_move

    def refuse_two(source: Path, destination: Path) -> Path:
        if source.name == "two.md":
            raise _in_use(32)
        return real_move(source, destination)

    monkeypatch.setattr("microfiche.core.filer.safe_move", refuse_two)

    result = file_batch(Library(library), [(moved, _classified()), (stuck, _classified())])

    assert [failure.unit for failure in result.failed] == [stuck]
    assert (library / "_sorting" / "pack" / "two.md").exists()  # so the folder is not emptied, and not removed
    assert result.job is not None
    assert [event.action for event in result.job.moves] == ["move"]


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        pytest.param(_in_use(32), "it is open in another program; close it and sort again", marks=_WINDOWS_ONLY),
        pytest.param(_in_use(33), "it is open in another program; close it and sort again", marks=_WINDOWS_ONLY),
        (PermissionError(13, "Permission denied"), "permission denied"),
        (FileExistsError(17, "File exists"), "something took its place at the destination while sorting"),
        (OSError(5, "Input/output error"), "OSError: [Errno 5] Input/output error"),
    ],
)
def test_file_batch_failure_reason_is_plain_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: OSError, reason: str
) -> None:
    library = _library(tmp_path)
    unit = _file_unit(library, "reqs.md")

    def fail(source: Path, destination: Path) -> Path:
        raise error

    monkeypatch.setattr("microfiche.core.filer.safe_move", fail)

    result = file_batch(Library(library), [(unit, _classified())])

    assert [failure.reason for failure in result.failed] == [reason]


def test_file_batch_unreadable_source_fails_that_unit(tmp_path: Path) -> None:
    library = _library(tmp_path)
    vanished = _file_unit(library, "gone.md")
    vanished.source_path.unlink()  # removed after the scan
    other = _file_unit(library, "other.md")

    result = file_batch(Library(library), [(vanished, _classified()), (other, _classified())])

    assert [failure.unit for failure in result.failed] == [vanished]
    assert result.failed[0].reason.startswith("FileNotFoundError")
    assert (library / GROUP / REQUIREMENTS / "other.md").exists()


# endregion


# region rollback_job


def test_rollback_job_restores_pre_sort_tree(tmp_path: Path) -> None:
    library = _library(tmp_path)
    units = [_file_unit(library, "a.md", "alpha"), _file_unit(library, "b.md", "beta"), _folder_unit(library, "bundle")]
    before = _snapshot(library)
    job = file_batch(Library(library), [(unit, _classified()) for unit in units]).job
    assert job is not None
    assert _snapshot(library) != before

    rolled_back = rollback_job(Library(library), job.job_id)

    assert _snapshot(library) == before
    assert rolled_back.rolled_back_at is not None
    assert load_job(library / ".microfiche", job.job_id).rolled_back_at is not None


def test_rollback_job_updates_ledger_and_audit_log(tmp_path: Path) -> None:
    library = _library(tmp_path)
    job = file_batch(Library(library), [(_file_unit(library, "a.md"), _classified())]).job
    assert job is not None

    rollback_job(Library(library), job.job_id)

    ledger = Ledger(library / ".microfiche")
    assert ledger.current() == []
    assert [r.event for r in ledger.read_all()] == ["filed", "rolled_back"]
    audit_lines = (library / ".microfiche" / AUDIT_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    assert len(audit_lines) == 2
    assert f"job={job.job_id} rollback {GROUP}/{REQUIREMENTS}/a.md -> _sorting/a.md" in audit_lines[1]


def test_rollback_job_recreates_removed_folders_and_files(tmp_path: Path) -> None:
    library = _library(tmp_path)
    units = [_unit_from_folder(library, "pack/one.md"), _unit_from_folder(library, "pack/sub/two.md")]
    before_files = _snapshot(library)
    job = file_batch(Library(library), [(unit, _classified()) for unit in units]).job
    assert job is not None

    rollback_job(Library(library), job.job_id)

    assert (library / "_sorting" / "pack" / "sub").is_dir()
    assert _snapshot(library) == before_files
    audit = (library / ".microfiche" / AUDIT_LOG_FILENAME).read_text(encoding="utf-8")
    assert "restore_folder _sorting/pack -> -" in audit
    assert "restore_folder _sorting/pack/sub -> -" in audit


def test_rollback_job_retry_restores_folder_once(tmp_path: Path) -> None:
    library = _library(tmp_path)
    loose = _file_unit(library, "loose.md")
    from_folder = _unit_from_folder(library, "pack/one.md")
    job = file_batch(Library(library), [(loose, _classified()), (from_folder, _classified())]).job
    assert job is not None
    blocker = library / "_sorting" / "loose.md"  # something now sits where loose.md must go back to
    blocker.write_text("in the way", encoding="utf-8")
    # Events run newest first: the folder is restored, one.md goes back, then loose.md is refused.
    with pytest.raises(FileExistsError):
        rollback_job(Library(library), job.job_id)
    blocker.unlink()

    rollback_job(Library(library), job.job_id)

    audit = (library / ".microfiche" / AUDIT_LOG_FILENAME).read_text(encoding="utf-8")
    assert audit.count("restore_folder _sorting/pack -> -") == 1  # not recorded again on the retry
    assert (library / "_sorting" / "pack" / "one.md").exists()
    assert (library / "_sorting" / "loose.md").exists()


def test_rollback_job_twice_refused(tmp_path: Path) -> None:
    library = _library(tmp_path)
    job = file_batch(Library(library), [(_file_unit(library, "a.md"), _classified())]).job
    assert job is not None
    rollback_job(Library(library), job.job_id)

    with pytest.raises(JobAlreadyRolledBackError):
        rollback_job(Library(library), job.job_id)


@pytest.mark.parametrize("job_id", ["no-such-job", "../escape", ""])
def test_rollback_job_unknown_job_id_raises_not_found(tmp_path: Path, job_id: str) -> None:
    library = _library(tmp_path)

    with pytest.raises(JobNotFoundError):
        rollback_job(Library(library), job_id)


def test_rollback_job_partial_retries_after_blocker_removed(tmp_path: Path) -> None:
    library = _library(tmp_path)
    first = _file_unit(library, "first.md")
    second = _file_unit(library, "second.md")
    before = _snapshot(library)
    job = file_batch(Library(library), [(first, _classified()), (second, _classified())]).job
    assert job is not None
    # Something new now occupies the first unit's original location, so reversing it must fail.
    blocker = library / "_sorting" / "first.md"
    blocker.write_text("blocker", encoding="utf-8")

    with pytest.raises(FileExistsError):
        rollback_job(Library(library), job.job_id)

    assert (library / "_sorting" / "second.md").exists()  # the newer move was already reversed
    assert load_job(library / ".microfiche", job.job_id).rolled_back_at is None
    assert [r.path for r in Ledger(library / ".microfiche").current()] == [f"{GROUP}/{REQUIREMENTS}/first.md"]

    blocker.unlink()
    rollback_job(Library(library), job.job_id)

    assert _snapshot(library) == before
    assert Ledger(library / ".microfiche").current() == []


def test_rollback_job_vanished_unit_raises(tmp_path: Path) -> None:
    library = _library(tmp_path)
    job = file_batch(Library(library), [(_file_unit(library, "a.md"), _classified())]).job
    assert job is not None
    (library / GROUP / REQUIREMENTS / "a.md").unlink()

    with pytest.raises(JobMoveMissingError):
        rollback_job(Library(library), job.job_id)

    assert load_job(library / ".microfiche", job.job_id).rolled_back_at is None


def test_rollback_job_invalid_config_still_works(tmp_path: Path) -> None:
    library = _library(tmp_path)
    job = file_batch(Library(library), [(_file_unit(library, "a.md"), _classified())]).job
    assert job is not None
    (library / ".microfiche" / "microfiche-config.toml").write_text("this is [not valid toml", encoding="utf-8")

    rollback_job(Library(library), job.job_id)  # needs only paths, so never reads the config

    assert (library / "_sorting" / "a.md").exists()


# endregion


# region latest_job


def _saved_job(library: Path, job_id: str, created: datetime, *, rolled_back: bool = False) -> Job:
    job = Job(job_id=job_id, created_at=created, rolled_back_at=created if rolled_back else None)
    save_job(library / ".microfiche", job)
    return job


def test_latest_job_skips_rolled_back_picks_newest_applied(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _saved_job(library, "old", datetime(2026, 1, 1, 9))
    _saved_job(library, "newer", datetime(2026, 1, 2, 9))
    _saved_job(library, "newest-undone", datetime(2026, 1, 3, 9), rolled_back=True)

    assert latest_job(library / ".microfiche").job_id == "newer"


def test_latest_job_orders_by_created_not_file_name(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _saved_job(library, "zzz", datetime(2026, 1, 1, 9))  # sorts last by name, but is the older job
    _saved_job(library, "aaa", datetime(2026, 1, 2, 9))

    assert latest_job(library / ".microfiche").job_id == "aaa"


def test_latest_job_no_jobs_raises(tmp_path: Path) -> None:
    with pytest.raises(NoJobToRollBackError):
        latest_job(_library(tmp_path) / ".microfiche")


def test_latest_job_all_rolled_back_raises(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _saved_job(library, "done", datetime(2026, 1, 1, 9), rolled_back=True)

    with pytest.raises(NoJobToRollBackError):
        latest_job(library / ".microfiche")


def test_latest_job_unreadable_file_skipped_with_a_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    library = _library(tmp_path)
    _saved_job(library, "good", datetime(2026, 1, 1, 9))
    broken = library / ".microfiche" / "rollback" / "job_broken.json"
    broken.write_text('{"job_id": "broken", "moves": [', encoding="utf-8")  # truncated

    with caplog.at_level(logging.WARNING, logger="microfiche.core"):
        job = latest_job(library / ".microfiche")

    assert job.job_id == "good"
    assert any("job_broken.json" in record.getMessage() for record in caplog.records)


def test_latest_job_only_unreadable_files_says_so(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / ".microfiche" / "rollback").mkdir(parents=True)
    (library / ".microfiche" / "rollback" / "job_broken.json").write_text("not json", encoding="utf-8")

    with pytest.raises(NoJobToRollBackError, match=r"job_broken\.json"):
        latest_job(library / ".microfiche")


# endregion


# region DestinationClaims


def test_destination_claims_free_path_claimed_once(tmp_path: Path) -> None:
    library = Library(_library(tmp_path))
    claims = DestinationClaims(library)
    destination = library.target_dir(GROUP, ARCHITECTURE) / "note.md"

    assert claims.claim(destination) is None

    reason = claims.claim(destination)
    assert reason == "another unit in this run is already going to Project Phoenix/02 Architecture/note.md"


def test_destination_claims_existing_path_refused_with_reason(tmp_path: Path) -> None:
    library = Library(_library(tmp_path))
    destination = library.target_dir(GROUP, ARCHITECTURE) / "note.md"
    destination.write_text("already here", encoding="utf-8")

    reason = DestinationClaims(library).claim(destination)

    assert reason == "'note.md' already exists in Project Phoenix/02 Architecture"


def test_destination_claims_refused_path_stays_unreserved(tmp_path: Path) -> None:
    library = Library(_library(tmp_path))
    claims = DestinationClaims(library)
    destination = library.target_dir(GROUP, ARCHITECTURE) / "note.md"
    destination.write_text("already here", encoding="utf-8")
    assert claims.claim(destination) is not None
    destination.unlink()  # whatever held it has gone

    assert claims.claim(destination) is None


def test_destination_claims_existing_folder_refused(tmp_path: Path) -> None:
    library = Library(_library(tmp_path))
    destination = library.target_dir(GROUP, ARCHITECTURE) / "bundle"
    destination.mkdir()

    assert DestinationClaims(library).claim(destination) == "'bundle' already exists in Project Phoenix/02 Architecture"


# endregion


# endregion


# region Logging


def test_file_batch_logs_each_move_and_a_summary(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    library = _library(tmp_path)
    units = [_file_unit(library, "a.md"), _file_unit(library, "b.md")]
    caplog.set_level(logging.DEBUG, logger="microfiche.core")

    job = file_batch(Library(library), [(unit, _classified()) for unit in units]).job

    assert job is not None
    assert f"moved _sorting/a.md -> {GROUP}/{REQUIREMENTS}/a.md" in caplog.messages
    assert f"moved _sorting/b.md -> {GROUP}/{REQUIREMENTS}/b.md" in caplog.messages
    assert f"filed 2 unit(s) as job {job.job_id}" in caplog.messages


def test_file_batch_logs_a_removed_empty_folder(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    library = _library(tmp_path)
    unit = _unit_from_folder(library, "pack/one.md")
    caplog.set_level(logging.DEBUG, logger="microfiche.core")

    file_batch(Library(library), [(unit, _classified())])

    assert "removed empty folder _sorting/pack" in caplog.messages


def test_file_batch_summary_is_info_and_moves_are_debug(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    library = _library(tmp_path)
    caplog.set_level(logging.INFO, logger="microfiche.core")

    file_batch(Library(library), [(_file_unit(library, "a.md"), _classified())])

    assert any(message.startswith("filed 1 unit(s) as job") for message in caplog.messages)
    assert not any(message.startswith("moved ") for message in caplog.messages)


def test_file_batch_failed_move_is_logged_with_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    library = _library(tmp_path)
    stuck = _file_unit(library, "stuck.docx")

    def refuse(source: Path, destination: Path) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("microfiche.core.filer.safe_move", refuse)
    caplog.set_level(logging.DEBUG, logger="microfiche.core")

    file_batch(Library(library), [(stuck, _classified())])

    [record] = [r for r in caplog.records if r.name == "microfiche.core.filer" and r.levelno >= logging.WARNING]
    assert "stuck.docx" in record.getMessage()
    assert "permission denied" in record.getMessage()  # the reason, as the report gives it


def test_file_batch_failed_move_logs_no_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    library = _library(tmp_path)

    def refuse(source: Path, destination: Path) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("microfiche.core.filer.safe_move", refuse)
    caplog.set_level(logging.DEBUG, logger="microfiche.core")

    file_batch(Library(library), [(_file_unit(library, "stuck.docx"), _classified())])

    assert not any(message.startswith(("moved ", "filed ")) for message in caplog.messages)


def test_rollback_job_logs_start_each_move_and_finish(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    library = _library(tmp_path)
    job = file_batch(Library(library), [(_file_unit(library, "a.md"), _classified())]).job
    assert job is not None
    caplog.set_level(logging.DEBUG, logger="microfiche.core")

    rollback_job(Library(library), job.job_id)

    assert f"rolling back job {job.job_id}: 1 recorded step(s)" in caplog.messages
    assert f"moved back {GROUP}/{REQUIREMENTS}/a.md -> _sorting/a.md" in caplog.messages
    assert f"rolled back job {job.job_id}: 1 step(s) reversed" in caplog.messages


# endregion
