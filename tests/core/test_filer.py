"""Tests for filing a batch of classified units and rolling the job back."""

from pathlib import Path

import pytest
from core.filer import (
    AUDIT_LOG_FILENAME,
    JobAlreadyRolledBackError,
    JobMoveMissingError,
    JobNotFoundError,
    UnresolvedClassificationError,
    file_batch,
    load_job,
    rollback_job,
)
from core.ledger import Ledger
from core.models.classification import CategoryMatch, ClassificationResult, GroupMatch
from core.models.document import Document
from core.models.unit import SortableUnit
from core.utils.hashing import file_hash, unit_hash

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


def test_file_batch_moves_each_unit_to_its_group_and_category(tmp_path: Path) -> None:
    library = _library(tmp_path)
    requirements = _file_unit(library, "reqs.md")
    design = _file_unit(library, "design.md")

    job = file_batch(library, [(requirements, _classified()), (design, _classified(ARCHITECTURE))])

    assert job is not None
    assert (library / GROUP / REQUIREMENTS / "reqs.md").read_text(encoding="utf-8") == "some content"
    assert (library / GROUP / ARCHITECTURE / "design.md").exists()
    assert not (library / "_sorting" / "reqs.md").exists()
    assert [move.action for move in job.moves] == ["move", "move"]


def test_file_batch_writes_no_sidecar_files(tmp_path: Path) -> None:
    library = _library(tmp_path)

    file_batch(library, [(_file_unit(library, "reqs.md"), _classified())])

    assert list(library.rglob("*.metadata.json")) == []


def test_file_batch_with_nothing_to_file_writes_nothing(tmp_path: Path) -> None:
    library = _library(tmp_path)

    assert file_batch(library, []) is None
    assert not (library / ".microfiche").exists()


def test_file_batch_applies_naming_rules(tmp_path: Path) -> None:
    library = _library(tmp_path)

    file_batch(library, [(_file_unit(library, "draft_reqs.md"), _classified())], naming_rules={"^draft_": "final_"})

    assert (library / GROUP / REQUIREMENTS / "final_reqs.md").exists()


def test_file_batch_saves_a_loadable_job(tmp_path: Path) -> None:
    library = _library(tmp_path)

    job = file_batch(library, [(_file_unit(library, "reqs.md"), _classified())])

    assert job is not None
    loaded = load_job(library / ".microfiche", job.job_id)
    assert loaded == job
    assert loaded.rolled_back_at is None


def test_file_batch_records_what_was_filed_and_why_in_the_ledger(tmp_path: Path) -> None:
    library = _library(tmp_path)
    unit = _file_unit(library, "reqs.md", text="hash me")
    expected_hash = file_hash(unit.source_path)

    job = file_batch(library, [(unit, _classified())])

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


def test_file_batch_appends_one_readable_audit_line_per_move(tmp_path: Path) -> None:
    library = _library(tmp_path)

    job = file_batch(
        library, [(_file_unit(library, "a.md"), _classified()), (_file_unit(library, "b.md"), _classified())]
    )

    assert job is not None
    lines = (library / ".microfiche" / AUDIT_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(f"job={job.job_id} move _sorting/" in line for line in lines)
    assert lines[0].endswith(f"_sorting/a.md -> {GROUP}/{REQUIREMENTS}/a.md")


def test_an_unresolved_classification_aborts_the_whole_batch_before_anything_moves(tmp_path: Path) -> None:
    library = _library(tmp_path)
    good = _file_unit(library, "good.md")
    bad = _file_unit(library, "bad.md")

    with pytest.raises(UnresolvedClassificationError):
        file_batch(library, [(good, _classified()), (bad, _classified(category=None))])

    assert good.source_path.exists()
    assert bad.source_path.exists()
    assert not (library / ".microfiche").exists()


def test_a_folder_unit_is_filed_whole_and_hashed_as_a_manifest(tmp_path: Path) -> None:
    library = _library(tmp_path)
    unit = _folder_unit(library, "bundle")
    expected_hash = unit_hash(unit.source_path)

    file_batch(library, [(unit, _classified())])

    assert (library / GROUP / REQUIREMENTS / "bundle" / "nested" / "two.md").exists()
    (record,) = Ledger(library / ".microfiche").current()
    assert record.unit_type == "folder"
    assert record.content_hash == expected_hash == unit_hash(library / record.path)


def test_a_destination_collision_keeps_earlier_moves_in_a_saved_job_that_can_be_rolled_back(tmp_path: Path) -> None:
    library = _library(tmp_path)
    first = _file_unit(library, "first.md")
    second = _file_unit(library, "second.md")
    (library / GROUP / ARCHITECTURE / "second.md").write_text("already here", encoding="utf-8")
    before = _snapshot(library)

    with pytest.raises(FileExistsError):
        file_batch(library, [(first, _classified()), (second, _classified(ARCHITECTURE))])

    assert (library / GROUP / REQUIREMENTS / "first.md").exists()
    assert second.source_path.exists()
    assert (library / GROUP / ARCHITECTURE / "second.md").read_text(encoding="utf-8") == "already here"
    assert [r.path for r in Ledger(library / ".microfiche").current()] == [f"{GROUP}/{REQUIREMENTS}/first.md"]
    (job_file,) = (library / ".microfiche" / "rollback").glob("job_*.json")

    rollback_job(library, job_file.stem.removeprefix("job_"))

    assert _snapshot(library) == before


def test_rollback_restores_the_exact_pre_sort_tree(tmp_path: Path) -> None:
    library = _library(tmp_path)
    units = [_file_unit(library, "a.md", "alpha"), _file_unit(library, "b.md", "beta"), _folder_unit(library, "bundle")]
    before = _snapshot(library)
    job = file_batch(library, [(unit, _classified()) for unit in units])
    assert job is not None
    assert _snapshot(library) != before

    rolled_back = rollback_job(library, job.job_id)

    assert _snapshot(library) == before
    assert rolled_back.rolled_back_at is not None
    assert load_job(library / ".microfiche", job.job_id).rolled_back_at is not None


def test_rollback_updates_the_ledger_and_the_audit_log(tmp_path: Path) -> None:
    library = _library(tmp_path)
    job = file_batch(library, [(_file_unit(library, "a.md"), _classified())])
    assert job is not None

    rollback_job(library, job.job_id)

    ledger = Ledger(library / ".microfiche")
    assert ledger.current() == []
    assert [r.event for r in ledger.read_all()] == ["filed", "rolled_back"]
    audit_lines = (library / ".microfiche" / AUDIT_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    assert len(audit_lines) == 2
    assert f"job={job.job_id} rollback {GROUP}/{REQUIREMENTS}/a.md -> _sorting/a.md" in audit_lines[1]


def test_rolling_back_twice_is_refused(tmp_path: Path) -> None:
    library = _library(tmp_path)
    job = file_batch(library, [(_file_unit(library, "a.md"), _classified())])
    assert job is not None
    rollback_job(library, job.job_id)

    with pytest.raises(JobAlreadyRolledBackError):
        rollback_job(library, job.job_id)


@pytest.mark.parametrize("job_id", ["no-such-job", "../escape", ""])
def test_rolling_back_an_unknown_or_malformed_job_id_raises_job_not_found(tmp_path: Path, job_id: str) -> None:
    library = _library(tmp_path)

    with pytest.raises(JobNotFoundError):
        rollback_job(library, job_id)


def test_rollback_that_stops_part_way_can_be_retried_once_the_blocker_is_removed(tmp_path: Path) -> None:
    library = _library(tmp_path)
    first = _file_unit(library, "first.md")
    second = _file_unit(library, "second.md")
    before = _snapshot(library)
    job = file_batch(library, [(first, _classified()), (second, _classified())])
    assert job is not None
    # Something new now occupies the first unit's original location, so reversing it must fail.
    blocker = library / "_sorting" / "first.md"
    blocker.write_text("blocker", encoding="utf-8")

    with pytest.raises(FileExistsError):
        rollback_job(library, job.job_id)

    assert (library / "_sorting" / "second.md").exists()  # the newer move was already reversed
    assert load_job(library / ".microfiche", job.job_id).rolled_back_at is None
    assert [r.path for r in Ledger(library / ".microfiche").current()] == [f"{GROUP}/{REQUIREMENTS}/first.md"]

    blocker.unlink()
    rollback_job(library, job.job_id)

    assert _snapshot(library) == before
    assert Ledger(library / ".microfiche").current() == []


def test_rollback_raises_when_a_filed_unit_has_vanished(tmp_path: Path) -> None:
    library = _library(tmp_path)
    job = file_batch(library, [(_file_unit(library, "a.md"), _classified())])
    assert job is not None
    (library / GROUP / REQUIREMENTS / "a.md").unlink()

    with pytest.raises(JobMoveMissingError):
        rollback_job(library, job.job_id)

    assert load_job(library / ".microfiche", job.job_id).rolled_back_at is None
