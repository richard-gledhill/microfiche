"""Tests for noticing filed units that were moved, edited or removed by hand."""

import shutil
from pathlib import Path

import pytest
from microfiche.core.drift import DriftState, check_drift, find_modified, record_moves
from microfiche.core.filer import JobMoveMissingError, rollback_job
from microfiche.core.ledger import Ledger
from microfiche.core.library.library import Library
from microfiche.core.organizer import run_sort

# region Test helpers


_MOCK_LIBRARY = Path(__file__).resolve().parents[1] / "mock_library"
_NOTE = "PhoenixArchitectureNotes.md"
_PACK = "phoenix-weekly-pack"
_FILED = Path("Project Phoenix") / "02 Architecture" / _NOTE
_ELSEWHERE = Path("Project Phoenix") / "03 Research" / _NOTE


def _sorted_library(tmp_path: Path, *, with_pack: bool = False) -> Library:
    """A copy of the mock library after one ``sort``, so the ledger has what it filed."""

    root = tmp_path / "library"
    shutil.copytree(_MOCK_LIBRARY, root)
    if not with_pack:
        shutil.rmtree(root / "_sorting" / _PACK)
    library = Library(root)
    run_sort(library)
    return library


def _move_by_hand(library: Library, source: Path, target: Path) -> None:
    (library.root / target).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(library.root / source, library.root / target)


# endregion

# region check_drift


def test_check_drift_everything_in_place_reports_nothing(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)

    report = check_drift(library)

    assert report.items == []
    assert report.summary is None


def test_check_drift_file_moved_by_hand_found_by_content(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)
    _move_by_hand(library, _FILED, _ELSEWHERE)

    report = check_drift(library)

    ((item),) = report.items
    assert (item.state, item.path, item.new_path) == (DriftState.MOVED, _FILED.as_posix(), _ELSEWHERE.as_posix())
    assert report.summary == "1 filed item: 1 moved"


def test_check_drift_file_moved_and_renamed_still_found(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)
    _move_by_hand(library, _FILED, Path("Project Phoenix") / "03 Research" / "renamed.md")

    (item,) = check_drift(library).items

    assert item.state is DriftState.MOVED
    assert item.new_path == "Project Phoenix/03 Research/renamed.md"


def test_check_drift_deleted_file_is_missing(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)
    (library.root / _FILED).unlink()

    (item,) = check_drift(library).items

    assert (item.state, item.new_path) == (DriftState.MISSING, None)


def test_check_drift_moved_and_edited_file_is_missing_not_guessed(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)
    _move_by_hand(library, _FILED, _ELSEWHERE)
    (library.root / _ELSEWHERE).write_text("Edited since.", encoding="utf-8")

    (item,) = check_drift(library).items

    assert item.state is DriftState.MISSING


def test_check_drift_two_copies_elsewhere_is_ambiguous_so_missing(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)
    _move_by_hand(library, _FILED, _ELSEWHERE)
    shutil.copy(library.root / _ELSEWHERE, library.root / "Project Phoenix" / "01 Requirements" / "copy.md")

    (item,) = check_drift(library).items

    assert item.state is DriftState.MISSING


def test_check_drift_edited_in_place_is_not_found_without_reading(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)
    (library.root / _FILED).write_text("Edited in place.", encoding="utf-8")

    assert check_drift(library).items == []  # nothing missing, so no file is read


def test_check_drift_folder_filed_whole_and_moved_by_hand_found(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path, with_pack=True)
    bundle = next(record for record in Ledger(library.state_dir).current() if record.unit_type == "folder")
    target = Path("Project Phoenix") / "03 Research" / Path(bundle.path).name
    _move_by_hand(library, Path(bundle.path), target)

    (item,) = check_drift(library).items

    assert (item.state, item.new_path) == (DriftState.MOVED, target.as_posix())


# endregion

# region record_moves and the ledger


def test_record_moves_ledger_points_at_new_place_and_second_check_is_clean(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)
    _move_by_hand(library, _FILED, _ELSEWHERE)
    report = check_drift(library)

    record_moves(library, report)

    assert report.recorded
    assert report.summary == "1 filed item: 1 moved; recorded"
    current = {record.path: record for record in Ledger(library.state_dir).current()}
    assert _ELSEWHERE.as_posix() in current
    assert _FILED.as_posix() not in current
    assert current[_ELSEWHERE.as_posix()].group == "Project Phoenix"  # classification carried over
    assert check_drift(library).items == []


def test_record_moves_missing_items_are_never_recorded(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)
    (library.root / _FILED).unlink()
    report = check_drift(library)

    record_moves(library, report)

    assert report.recorded is False
    assert [r.event for r in Ledger(library.state_dir).read_all()] == ["filed"]


def test_ledger_relocations_follow_a_unit_moved_twice(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)
    second = Path("Project Phoenix") / "01 Requirements" / _NOTE
    _move_by_hand(library, _FILED, _ELSEWHERE)
    record_moves(library, check_drift(library))
    _move_by_hand(library, _ELSEWHERE, second)
    record_moves(library, check_drift(library))

    chains = Ledger(library.state_dir).relocations()

    assert chains == {_FILED.as_posix(): [_FILED.as_posix(), _ELSEWHERE.as_posix(), second.as_posix()]}


def test_find_modified_reports_only_files_whose_content_changed(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)
    (library.root / _FILED).write_text("Edited in place.", encoding="utf-8")

    modified = find_modified(library, [library.root / _FILED])

    assert [(i.path, i.state) for i in modified] == [(_FILED.as_posix(), DriftState.MODIFIED)]


def test_find_modified_unchanged_file_not_reported(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)

    assert find_modified(library, [library.root / _FILED]) == []


# endregion

# region rollback after drift


def _job_id(library: Library) -> str:
    (record,) = [r for r in Ledger(library.state_dir).read_all() if r.event == "filed" and r.path == _FILED.as_posix()]
    return record.job_id


def test_rollback_restores_a_file_moved_by_hand_from_its_new_place(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)
    job_id = _job_id(library)
    _move_by_hand(library, _FILED, _ELSEWHERE)
    record_moves(library, check_drift(library))

    rollback_job(library, job_id)

    assert (library.root / "_sorting" / _NOTE).is_file()
    assert not (library.root / _ELSEWHERE).exists()
    assert Ledger(library.state_dir).current() == []  # every hop is rolled back


def test_rollback_missing_file_stops_before_moving_anything_and_names_it(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)
    job_id = _job_id(library)
    (library.root / _FILED).unlink()

    with pytest.raises(JobMoveMissingError) as caught:
        rollback_job(library, job_id)

    assert _NOTE in str(caught.value)
    assert not (library.root / "_sorting" / _NOTE).exists()
    assert len(Ledger(library.state_dir).current()) == 1  # still filed: nothing was recorded as rolled back


def test_rollback_edited_file_is_moved_back_and_listed(tmp_path: Path) -> None:
    library = _sorted_library(tmp_path)
    job_id = _job_id(library)
    (library.root / _FILED).write_text("Edited in place.", encoding="utf-8")
    edited: list[str] = []

    rollback_job(library, job_id, edited=edited)

    assert edited == [_FILED.as_posix()]
    assert (library.root / "_sorting" / _NOTE).read_text(encoding="utf-8") == "Edited in place."


# endregion
