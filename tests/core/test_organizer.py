"""Tests for the `sort` pipeline: scan -> classify -> file as one job, leaving the rest for review."""

import shutil
from pathlib import Path

from core.config import MICROFICHE_DIRNAME, load_config
from core.filer import AUDIT_LOG_FILENAME, rollback_job
from core.ledger import Ledger
from core.organizer import run_sort
from core.utils.hashing import file_hash

_MOCK_LIBRARY = Path(__file__).resolve().parents[1] / "mock_library"

# In the mock library, this note names "Project Phoenix" and "architecture", so it files
# confidently; the solar note names no known group, so it must go to review.
_PHOENIX_NOTE = "PhoenixArchitectureNotes.md"
_SOLAR_NOTE = "SolarConstructionNotes.md"
_PHOENIX_DESTINATION = Path("Project Phoenix") / "02 Architecture" / _PHOENIX_NOTE


def _library(tmp_path: Path) -> Path:
    library = tmp_path / "library"
    shutil.copytree(_MOCK_LIBRARY, library)
    return library


def _snapshot(library: Path) -> dict[str, str]:
    """Library-relative path -> hash for every file, ignoring microfiche's own state."""

    state_dir = library / MICROFICHE_DIRNAME
    return {
        path.relative_to(library).as_posix(): file_hash(path)
        for path in sorted(library.rglob("*"))
        if path.is_file() and not path.is_relative_to(state_dir)
    }


def test_sort_files_confident_units_and_leaves_the_rest_in_the_inbox_for_review(tmp_path: Path) -> None:
    library = _library(tmp_path)

    report = run_sort(library, load_config(library / MICROFICHE_DIRNAME))

    assert [unit.source_path.name for unit, _ in report.filed] == [_PHOENIX_NOTE]
    assert [unit.source_path.name for unit, _ in report.needs_review] == [_SOLAR_NOTE]
    assert (library / _PHOENIX_DESTINATION).exists()
    assert not (library / "_sorting" / _PHOENIX_NOTE).exists()
    assert (library / "_sorting" / _SOLAR_NOTE).exists()


def test_sort_records_one_job_covering_everything_it_filed(tmp_path: Path) -> None:
    library = _library(tmp_path)

    report = run_sort(library, load_config(library / MICROFICHE_DIRNAME))

    assert report.job is not None
    assert [move.new_path for move in report.job.moves] == [library / _PHOENIX_DESTINATION]
    assert report.audit_events == report.job.moves
    assert (library / MICROFICHE_DIRNAME / "rollback" / f"job_{report.job.job_id}.json").exists()
    (record,) = Ledger(library / MICROFICHE_DIRNAME).current()
    assert record.job_id == report.job.job_id
    assert record.path == _PHOENIX_DESTINATION.as_posix()
    assert (record.group, record.category) == ("Project Phoenix", "02 Architecture")
    assert (library / MICROFICHE_DIRNAME / AUDIT_LOG_FILENAME).read_text(encoding="utf-8").count("\n") == 1


def test_units_sent_to_review_are_not_moved_or_recorded(tmp_path: Path) -> None:
    library = _library(tmp_path)

    run_sort(library, load_config(library / MICROFICHE_DIRNAME))

    recorded = [record.original_path for record in Ledger(library / MICROFICHE_DIRNAME).read_all()]
    assert recorded == [f"_sorting/{_PHOENIX_NOTE}"]


def test_sort_with_nothing_confident_enough_writes_no_job_ledger_or_audit_log(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / "_sorting" / _PHOENIX_NOTE).unlink()
    before = _snapshot(library)

    report = run_sort(library, load_config(library / MICROFICHE_DIRNAME))

    assert report.job is None
    assert report.filed == []
    assert report.audit_events == []
    assert [unit.source_path.name for unit, _ in report.needs_review] == [_SOLAR_NOTE]
    assert _snapshot(library) == before
    state_dir = library / MICROFICHE_DIRNAME
    assert not (state_dir / "rollback").exists()
    assert not (state_dir / AUDIT_LOG_FILENAME).exists()
    assert not Ledger(state_dir).path.exists()


def test_sort_without_an_inbox_does_nothing(tmp_path: Path) -> None:
    library = _library(tmp_path)
    shutil.rmtree(library / "_sorting")

    report = run_sort(library, load_config(library / MICROFICHE_DIRNAME))

    assert report.job is None
    assert report.filed == []
    assert report.needs_review == []


def test_a_folder_in_the_inbox_is_filed_whole_when_keep_folders_is_set(tmp_path: Path) -> None:
    library = _library(tmp_path)
    bundle = library / "_sorting" / "phoenix-bundle"
    bundle.mkdir()
    (bundle / "overview.md").write_text("Project Phoenix architecture overview.", encoding="utf-8")
    (bundle / "decisions.md").write_text("Project Phoenix architecture decisions.", encoding="utf-8")

    report = run_sort(library, load_config(library / MICROFICHE_DIRNAME), keep_folders=True)

    destination = library / "Project Phoenix" / "02 Architecture" / "phoenix-bundle"
    assert (destination / "overview.md").exists()
    assert (destination / "decisions.md").exists()
    assert not bundle.exists()
    assert report.job is not None
    folder_records = [r for r in Ledger(library / MICROFICHE_DIRNAME).current() if r.unit_type == "folder"]
    assert [r.path for r in folder_records] == ["Project Phoenix/02 Architecture/phoenix-bundle"]


def test_a_sort_can_be_rolled_back_to_the_exact_pre_sort_library(tmp_path: Path) -> None:
    library = _library(tmp_path)
    before = _snapshot(library)
    report = run_sort(library, load_config(library / MICROFICHE_DIRNAME))
    assert report.job is not None
    assert _snapshot(library) != before

    rollback_job(library, report.job.job_id)

    assert _snapshot(library) == before
    assert Ledger(library / MICROFICHE_DIRNAME).current() == []
