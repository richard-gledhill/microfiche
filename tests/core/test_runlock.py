"""Tests for the run lock that stops two runs from changing one library at once."""

import json
import multiprocessing
import os
import threading
from datetime import datetime
from multiprocessing.synchronize import Event
from pathlib import Path

import pytest
from microfiche.core.library.library import Library
from microfiche.core.runlock import LOCK_FILENAME, LockHolder, LockUnavailableError, RunLockedError, run_lock

# region Test helpers


def _library(tmp_path: Path) -> Library:
    return Library(tmp_path / "library")


def _lock_path(library: Library) -> Path:
    return library.state_dir / LOCK_FILENAME


def _write_lock(library: Library, **details: object) -> Path:
    """A lock file as a run would have left it, with ``details`` overriding a live ``sort`` run's."""

    path = _lock_path(library)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"pid": os.getpid(), "command": "sort", "started": "2026-10-12T09:30:00+11:00", **details}),
        encoding="utf-8",
    )
    return path


def _hold_lock_in_another_process(root: str, held: Event, release: Event) -> None:
    """Take the lock in a separate process, say so, and keep it until told to let go.

    Module-level so that the spawned process can find it by name.
    """

    with run_lock(Library(Path(root)), "reclassify"):
        held.set()
        release.wait(30)


# endregion


# region Public API


# region run_lock


def test_run_lock_held_writes_lock_file_and_removes_it_after(tmp_path: Path) -> None:
    library = _library(tmp_path)

    with run_lock(library, "sort"):
        details = json.loads(_lock_path(library).read_text(encoding="utf-8"))

    assert details["pid"] == os.getpid()
    assert details["command"] == "sort"
    assert details["started"]  # an ISO timestamp
    assert not _lock_path(library).exists()


def test_run_lock_released_when_the_run_raises(tmp_path: Path) -> None:
    library = _library(tmp_path)
    failure = RuntimeError("the run failed")

    with pytest.raises(RuntimeError, match="the run failed"), run_lock(library, "sort"):
        raise failure

    assert not _lock_path(library).exists()


def test_run_lock_creates_missing_state_folder(tmp_path: Path) -> None:
    library = _library(tmp_path)
    assert not library.state_dir.exists()

    with run_lock(library, "sort"):
        assert _lock_path(library).exists()


def test_run_lock_second_run_refused_with_who_holds_it(tmp_path: Path) -> None:
    library = _library(tmp_path)

    with run_lock(library, "sort"), pytest.raises(RunLockedError) as refused, run_lock(library, "rollback"):
        pytest.fail("a second run must not start while the first holds the lock")

    message = str(refused.value)
    assert f"Another microfiche run is already in progress (sort, process {os.getpid()}, started " in message
    assert f"If no run is active, delete {_lock_path(library)} and try again." in message
    assert refused.value.holder is not None
    assert refused.value.holder.command == "sort"


def test_run_lock_refused_run_leaves_the_first_lock_in_place(tmp_path: Path) -> None:
    library = _library(tmp_path)

    with run_lock(library, "sort"):
        with pytest.raises(RunLockedError), run_lock(library, "rollback"):
            pass
        assert _lock_path(library).exists()
        assert json.loads(_lock_path(library).read_text(encoding="utf-8"))["command"] == "sort"


def test_run_lock_can_be_taken_again_after_release(tmp_path: Path) -> None:
    library = _library(tmp_path)
    with run_lock(library, "sort"):
        pass

    with run_lock(library, "rollback"):
        assert json.loads(_lock_path(library).read_text(encoding="utf-8"))["command"] == "rollback"


def test_run_lock_stale_lock_of_dead_process_taken_over(tmp_path: Path, dead_pid: int) -> None:
    library = _library(tmp_path)
    _write_lock(library, pid=dead_pid, command="sort")

    with run_lock(library, "rollback"):
        details = json.loads(_lock_path(library).read_text(encoding="utf-8"))
        assert (details["pid"], details["command"]) == (os.getpid(), "rollback")

    assert not _lock_path(library).exists()


def test_run_lock_yields_nothing_when_it_cleared_no_lock(tmp_path: Path) -> None:
    with run_lock(_library(tmp_path), "sort") as cleared:
        assert cleared is None


def test_run_lock_yields_the_holder_of_the_stale_lock_it_cleared(tmp_path: Path, dead_pid: int) -> None:
    # The lock cannot log this itself: it is taken before the CLI sets logging up. So it hands the fact to its caller.
    library = _library(tmp_path)
    _write_lock(library, pid=dead_pid, command="reclassify", started="2026-10-12T09:30:00+11:00")

    with run_lock(library, "sort") as cleared:
        assert cleared == LockHolder(
            pid=dead_pid, command="reclassify", started=datetime.fromisoformat("2026-10-12T09:30:00+11:00")
        )


@pytest.mark.parametrize(
    "contents",
    ["", "not json at all", "[]", '{"command": "sort"}', '{"pid": "abc", "command": "sort", "started": "x"}'],
)
def test_run_lock_unreadable_lock_file_counts_as_held_and_is_kept(tmp_path: Path, contents: str) -> None:
    library = _library(tmp_path)
    path = _lock_path(library)
    path.parent.mkdir(parents=True)
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(RunLockedError) as refused, run_lock(library, "sort"):
        pass

    assert refused.value.holder is None
    assert "cannot be read" in str(refused.value)
    assert "delete that file" in str(refused.value)
    assert path.read_text(encoding="utf-8") == contents  # a lock that cannot be understood is never cleared


def test_run_lock_release_leaves_a_lock_someone_else_now_holds(tmp_path: Path, dead_pid: int) -> None:
    library = _library(tmp_path)

    with run_lock(library, "sort"):
        _write_lock(library, pid=dead_pid, command="elsewhere")  # the file was replaced under us

    assert json.loads(_lock_path(library).read_text(encoding="utf-8"))["command"] == "elsewhere"


def test_run_lock_state_folder_cannot_be_created_reports_why(tmp_path: Path) -> None:
    library = _library(tmp_path)
    library.root.mkdir()
    library.state_dir.write_text("a file where the state folder should be", encoding="utf-8")

    with pytest.raises(LockUnavailableError, match="Could not create the run lock"), run_lock(library, "sort"):
        pass


def test_run_lock_lock_file_cannot_be_created_reports_why(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> int:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("microfiche.core.runlock.os.open", refuse)

    with pytest.raises(LockUnavailableError, match="PermissionError"), run_lock(_library(tmp_path), "sort"):
        pass


def test_run_lock_write_failure_leaves_no_lock_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    failure = OSError(28, "No space left on device")

    def fail_to_write(*args: object, **kwargs: object) -> object:
        raise failure

    monkeypatch.setattr("microfiche.core.runlock.os.write", fail_to_write)

    with pytest.raises(LockUnavailableError, match="No space left"), run_lock(library, "sort"):
        pass

    assert not _lock_path(library).exists()  # an empty lock file would block every later run


def test_run_lock_many_runs_starting_together_only_one_gets_it(tmp_path: Path) -> None:
    library = _library(tmp_path)
    library.state_dir.mkdir(parents=True)
    runs = 12
    barrier = threading.Barrier(runs)
    outcomes: list[str] = []
    release = threading.Event()

    def start() -> None:
        barrier.wait()
        try:
            with run_lock(library, "sort"):
                outcomes.append("ran")
                release.wait(5)
        except RunLockedError:
            outcomes.append("refused")

    threads = [threading.Thread(target=start) for _ in range(runs)]
    for thread in threads:
        thread.start()
    while len(outcomes) < runs:  # the winner holds the lock until every other run has been turned away
        if outcomes.count("refused") == runs - 1:
            release.set()
        threading.Event().wait(0.01)
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["ran"] + ["refused"] * (runs - 1)


def test_run_lock_held_by_another_process_refuses_then_allows(tmp_path: Path) -> None:
    library = _library(tmp_path)
    context = multiprocessing.get_context("spawn")
    held, release = context.Event(), context.Event()
    other = context.Process(target=_hold_lock_in_another_process, args=(str(library.root), held, release))
    other.start()
    try:
        assert held.wait(60), "the other process never took the lock"

        with pytest.raises(RunLockedError) as refused, run_lock(library, "sort"):
            pass
        assert refused.value.holder is not None
        assert (refused.value.holder.pid, refused.value.holder.command) == (other.pid, "reclassify")
    finally:
        release.set()
        other.join(60)

    with run_lock(library, "sort"):  # the other run finished and released it
        pass


def test_run_lock_process_that_dies_holding_it_leaves_a_lock_that_is_cleared(tmp_path: Path) -> None:
    library = _library(tmp_path)
    context = multiprocessing.get_context("spawn")
    held, release = context.Event(), context.Event()
    other = context.Process(target=_hold_lock_in_another_process, args=(str(library.root), held, release))
    other.start()
    assert held.wait(60), "the other process never took the lock"
    other.terminate()  # killed: it never gets to release the lock
    other.join(60)
    assert _lock_path(library).exists()

    with run_lock(library, "sort"):  # the holder is gone, so the lock is stale
        assert json.loads(_lock_path(library).read_text(encoding="utf-8"))["pid"] == os.getpid()


# endregion


# endregion
