"""Tests for the append-only classification ledger."""

from pathlib import Path

import pytest
from core.ledger import Ledger, LedgerCorruptError
from core.models.ledger import LedgerEvent, LedgerRecord


def _record(
    path: str,
    *,
    event: LedgerEvent = "filed",
    job_id: str = "job1",
    original_path: str = "_sorting/doc.md",
    content_hash: str = "hash-a",
) -> LedgerRecord:
    return LedgerRecord(
        event=event,
        job_id=job_id,
        path=path,
        original_path=original_path,
        content_hash=content_hash,
        unit_type="file",
        group="Project Phoenix" if event == "filed" else None,
        category="01 Requirements" if event == "filed" else None,
        confidence=0.9 if event == "filed" else None,
    )


def test_ledger_no_file_empty(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")

    assert ledger.read_all() == []
    assert ledger.current() == []
    assert ledger.lookup("anything.md", "hash") is None


def test_append_nothing_creates_no_file(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")

    ledger.append([])

    assert not ledger.path.exists()
    assert not (tmp_path / ".microfiche").exists()


def test_append_writes_json_line_per_record_accumulating(tmp_path: Path) -> None:
    state_dir = tmp_path / ".microfiche"
    Ledger(state_dir).append([_record("G/C/a.md"), _record("G/C/b.md", content_hash="hash-b")])
    Ledger(state_dir).append([_record("G/C/c.md", job_id="job2", content_hash="hash-c")])

    ledger = Ledger(state_dir)

    assert [record.path for record in ledger.read_all()] == ["G/C/a.md", "G/C/b.md", "G/C/c.md"]
    assert len(ledger.path.read_text(encoding="utf-8").splitlines()) == 3


def test_append_unix_newlines_round_trips_non_ascii_paths(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")
    ledger.append([_record("Café/Résumés/naïve.md")])

    assert b"\r\n" not in ledger.path.read_bytes()
    assert ledger.read_all()[0].path == "Café/Résumés/naïve.md"


def test_current_keeps_latest_record_per_path(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")
    ledger.append([_record("G/C/a.md", job_id="job1", content_hash="old")])
    ledger.append([_record("G/C/a.md", job_id="job2", content_hash="new")])

    assert [(r.job_id, r.content_hash) for r in ledger.current()] == [("job2", "new")]


def test_current_rollback_hides_record_read_all_keeps_history(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")
    ledger.append([_record("G/C/a.md"), _record("G/C/b.md", content_hash="hash-b")])
    ledger.append([_record("G/C/a.md", event="rolled_back")])

    assert [r.path for r in ledger.current()] == ["G/C/b.md"]
    assert len(ledger.read_all()) == 3


def test_current_other_job_rollback_keeps_record(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")
    ledger.append([_record("G/C/a.md", job_id="job1")])
    ledger.append([_record("G/C/a.md", event="rolled_back", job_id="job-other")])

    assert [r.path for r in ledger.current()] == ["G/C/a.md"]


def test_current_refiled_after_rollback(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")
    ledger.append([_record("G/C/a.md", job_id="job1")])
    ledger.append([_record("G/C/a.md", event="rolled_back", job_id="job1")])
    ledger.append([_record("G/C/a.md", job_id="job2")])

    assert [r.job_id for r in ledger.current()] == ["job2"]


def test_current_moved_unit_supersedes_old_record(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")
    ledger.append([_record("G/Old/a.md", job_id="job1")])
    ledger.append([_record("G/New/a.md", job_id="job2", original_path="G/Old/a.md")])

    assert [r.path for r in ledger.current()] == ["G/New/a.md"]


def test_current_rolled_back_move_restores_old_record(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")
    ledger.append([_record("G/Old/a.md", job_id="job1")])
    ledger.append([_record("G/New/a.md", job_id="job2", original_path="G/Old/a.md")])
    ledger.append([_record("G/New/a.md", event="rolled_back", job_id="job2", original_path="G/Old/a.md")])

    assert [r.path for r in ledger.current()] == ["G/Old/a.md"]


def test_lookup_matches_on_path_and_hash(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")
    ledger.append([_record("G/C/a.md", content_hash="hash-a"), _record("G/C/b.md", content_hash="hash-b")])

    found = ledger.lookup("G/C/b.md", "hash-b")

    assert found is not None
    assert found.path == "G/C/b.md"


def test_lookup_finds_externally_moved_unit_by_hash(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")
    ledger.append([_record("G/C/a.md", content_hash="hash-a"), _record("G/C/b.md", content_hash="hash-b")])

    found = ledger.lookup("G/Elsewhere/renamed.md", "hash-a")

    assert found is not None
    assert found.path == "G/C/a.md"


def test_lookup_hash_alone_refused_for_duplicate_content(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")
    ledger.append([_record("G/C/a.md", content_hash="same"), _record("G/C/copy.md", content_hash="same")])

    assert ledger.lookup("G/Elsewhere/x.md", "same") is None
    exact = ledger.lookup("G/C/copy.md", "same")
    assert exact is not None
    assert exact.path == "G/C/copy.md"


def test_lookup_changed_content_no_match(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")
    ledger.append([_record("G/C/a.md", content_hash="hash-a")])

    assert ledger.lookup("G/C/a.md", "edited-hash") is None


def test_lookup_ignores_rolled_back_records(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")
    ledger.append([_record("G/C/a.md", content_hash="hash-a")])
    ledger.append([_record("G/C/a.md", event="rolled_back", content_hash="hash-a")])

    assert ledger.lookup("G/C/a.md", "hash-a") is None
    assert ledger.lookup("_sorting/a.md", "hash-a") is None


def test_unreadable_line_raises_with_line_number(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")
    ledger.append([_record("G/C/a.md")])
    with ledger.path.open("a", encoding="utf-8") as fh:
        fh.write("not json\n")

    with pytest.raises(LedgerCorruptError) as excinfo:
        ledger.current()

    assert excinfo.value.line_number == 2
    assert "line 2" in str(excinfo.value)


def test_blank_lines_ignored(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / ".microfiche")
    ledger.append([_record("G/C/a.md")])
    with ledger.path.open("a", encoding="utf-8") as fh:
        fh.write("\n   \n")

    assert len(ledger.read_all()) == 1
