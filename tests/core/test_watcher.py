"""Tests for the `watch` loop: stability, batching, held units, the lock timeout and stopping, all on a fake clock."""

from collections.abc import Callable
from pathlib import Path

import pytest
from microfiche.core.drift import DriftReport
from microfiche.core.duplicates import Duplicate
from microfiche.core.library.library import Library
from microfiche.core.models.classification import CategoryMatch, ClassificationResult, GroupMatch
from microfiche.core.models.unit import SortableUnit
from microfiche.core.organizer import SortReport
from microfiche.core.runlock import RunLockedError
from microfiche.core.scanner import InboxSnapshot
from microfiche.core.watcher import SystemClock, WatchBatch, Watcher

# region Test helpers

_INTERVAL = 60.0


class _FakeClock:
    """A clock that moves only when slept on, and can call a hook at each sleep."""

    def __init__(self) -> None:
        self.time = 0.0
        self.sleeps: list[float] = []
        self.on_sleep: list[Callable[[], None]] = []

    def now(self) -> float:
        return self.time

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.time += seconds
        if self.on_sleep:
            self.on_sleep.pop(0)()


def _classification() -> ClassificationResult:
    return ClassificationResult(
        group=GroupMatch(name=None, confidence=0.0, reason="none"),
        category=CategoryMatch(name=None, confidence=0.0, reason="none"),
        overall_confidence=0.0,
        classified_by="rules_engine",
        confident=False,
    )


class _Rig:
    """A watcher over a fake inbox: ``inbox`` is the snapshot the next scan sees, and ``batches`` what was filed.

    A batch removes each entry from the inbox, except the names in ``review`` or ``duplicates``, which it leaves
    held (``nested`` gives the file inside a folder that the unit was).
    """

    def __init__(self, tmp_path: Path) -> None:
        self.library = Library(tmp_path)
        self.inbox: InboxSnapshot = {}
        self.batches: list[tuple[Path, ...]] = []
        self.events: list[WatchBatch] = []
        self.review: set[str] = set()
        self.duplicates: set[str] = set()
        self.nested: dict[str, str] = {}
        self.lock_busy = False
        self.batch_error: Exception | None = None
        self.open_error: Exception | None = None
        self.during_batch: Callable[[], None] | None = None
        self.scans = 0
        self.clock = _FakeClock()
        self.watcher = Watcher(
            self._open,
            self._run,
            self.events.append,
            interval=_INTERVAL,
            snapshot=self._scan,
            clock=self.clock,
        )

    def put(self, name: str, version: int = 1) -> Path:
        entry = self.library.inbox / name
        self.inbox[entry] = ((name, version, 0),)
        return entry

    def step(self, times: int = 1) -> WatchBatch | None:
        batch = None
        for _ in range(times):
            batch = self.watcher.step()
        return batch

    def _open(self) -> Library:
        if self.open_error is not None:
            raise self.open_error
        return self.library

    def _scan(self, _library: Library) -> InboxSnapshot:
        self.scans += 1
        return dict(self.inbox)

    def _run(self, _library: Library, entries: tuple[Path, ...]) -> tuple[SortReport, DriftReport]:
        if self.lock_busy:
            raise RunLockedError(self.library.state_dir / "lock", None)
        if self.batch_error is not None:
            raise self.batch_error
        if self.during_batch is not None:
            self.during_batch()
        self.batches.append(entries)
        report = SortReport()
        for entry in entries:
            source = entry / self.nested[entry.name] if entry.name in self.nested else entry
            unit = SortableUnit(source_path=source, kind="file", documents=[])
            if entry.name in self.review:
                report.needs_review.append((unit, _classification()))
            elif entry.name in self.duplicates:
                report.duplicates.append(Duplicate(unit, _classification(), Path("elsewhere"), "a copy"))
            else:
                del self.inbox[entry]
        return report, DriftReport()


@pytest.fixture
def rig(tmp_path: Path) -> _Rig:
    return _Rig(tmp_path)


# endregion


# region Public API


# region Stability


def test_watcher_first_scan_files_nothing(rig: _Rig) -> None:
    rig.put("a.md")

    assert rig.step() is None
    assert rig.batches == []


def test_watcher_unit_unchanged_between_two_scans_filed(rig: _Rig) -> None:
    entry = rig.put("a.md")

    batch = rig.step(2)

    assert rig.batches == [(entry,)]
    assert batch is not None
    assert batch.report is not None
    assert batch.entries == (entry,)


def test_watcher_unit_still_changing_waits_until_it_stops(rig: _Rig) -> None:
    rig.put("slow.md", version=1)
    rig.step()
    rig.put("slow.md", version=2)  # still being written
    rig.step()
    rig.put("slow.md", version=3)
    rig.step()

    assert rig.batches == []

    rig.step()  # unchanged since the last scan

    assert len(rig.batches) == 1


def test_watcher_idle_scan_reports_nothing(rig: _Rig) -> None:
    rig.step(3)

    assert rig.events == []


# endregion


# region Batching


def test_watcher_new_arrival_holds_back_stable_units_until_a_quiet_scan(rig: _Rig) -> None:
    first = rig.put("first.md")
    rig.step()
    second = rig.put("second.md")  # lands while `first` is already settled
    rig.step()

    assert rig.batches == []

    rig.step()

    assert rig.batches == [(first, second)]


def test_watcher_ten_files_copied_in_file_as_one_batch(rig: _Rig) -> None:
    for number in range(10):
        rig.put(f"doc{number}.md")

    rig.step(2)

    assert len(rig.batches) == 1
    assert len(rig.batches[0]) == 10


def test_watcher_filed_units_not_filed_again(rig: _Rig) -> None:
    rig.put("a.md")
    rig.step(2)

    rig.step(3)

    assert len(rig.batches) == 1


# endregion


# region Held units


@pytest.mark.parametrize("kind", ["review", "duplicates"])
def test_watcher_held_unit_not_tried_again_while_unchanged(rig: _Rig, kind: str) -> None:
    rig.put("held.md")
    getattr(rig, kind).add("held.md")
    rig.step(2)

    rig.step(4)

    assert len(rig.batches) == 1


def test_watcher_held_unit_tried_again_once_it_changes(rig: _Rig) -> None:
    rig.put("held.md")
    rig.review.add("held.md")
    rig.step(2)
    rig.review.clear()
    rig.put("held.md", version=2)  # the person edited it

    rig.step(2)

    assert len(rig.batches) == 2


def test_watcher_held_unit_tried_again_when_config_changes(rig: _Rig) -> None:
    rig.put("held.md")
    rig.review.add("held.md")
    rig.step(2)
    rig.review.clear()
    config = rig.library.state_dir / "microfiche-config.toml"
    config.parent.mkdir(parents=True)
    config.write_text("[classification]\nconfidence_threshold = 0.7\n", encoding="utf-8")

    rig.step()

    assert len(rig.batches) == 2


def test_watcher_held_unit_tried_again_when_library_file_changes(rig: _Rig) -> None:
    rig.put("held.md")
    rig.review.add("held.md")
    rig.step(2)
    rig.review.clear()
    hints = rig.library.state_dir / "microfiche-library.json"
    hints.parent.mkdir(parents=True)
    hints.write_text("{}", encoding="utf-8")

    rig.step()

    assert len(rig.batches) == 2


def test_watcher_batch_own_library_file_update_does_not_free_held_units(rig: _Rig) -> None:
    state = rig.library.state_dir
    state.mkdir(parents=True)
    hints = state / "microfiche-library.json"
    hints.write_text("{}", encoding="utf-8")
    rig.put("held.md")
    rig.review.add("held.md")
    rig.step()
    rig.during_batch = lambda: hints.write_text('{"synced": true}', encoding="utf-8")  # `run_sort` syncs the file
    rig.step()

    rig.step(3)

    assert len(rig.batches) == 1


def test_watcher_held_file_in_folder_holds_that_folder(rig: _Rig) -> None:
    rig.put("folder")
    rig.nested["folder"] = "inside/doc.md"
    rig.review.add("folder")
    rig.step(2)

    rig.step(3)

    assert len(rig.batches) == 1


# endregion


# region The run lock


def test_watcher_lock_busy_skips_batch_and_tries_at_next_scan(rig: _Rig) -> None:
    entry = rig.put("a.md")
    rig.lock_busy = True
    rig.step()

    skipped = rig.step()

    assert skipped is not None
    assert skipped.skipped is not None
    assert skipped.report is None
    assert rig.batches == []

    rig.lock_busy = False
    filed = rig.step()

    assert filed is not None
    assert filed.report is not None
    assert rig.batches == [(entry,)]


# endregion


# region Failures


def test_watcher_batch_failure_reported_and_retried(rig: _Rig) -> None:
    entry = rig.put("a.md")
    rig.batch_error = OSError("disk gone")
    rig.step()

    failed = rig.step()

    assert failed is not None
    assert failed.error is not None
    assert "disk gone" in failed.error
    assert rig.events == [failed]

    rig.batch_error = None
    rig.step()

    assert rig.batches == [(entry,)]


def test_watcher_scan_failure_reported_and_watching_continues(rig: _Rig) -> None:
    rig.open_error = ValueError("config went bad")

    failed = rig.step()

    assert failed is not None
    assert failed.error is not None
    assert "config went bad" in failed.error
    assert failed.entries == ()


# endregion


# region Running and stopping


def test_watcher_run_waits_one_interval_between_scans_without_really_sleeping(rig: _Rig) -> None:
    rig.put("a.md")
    rig.during_batch = rig.watcher.stop

    rig.watcher.run()

    assert rig.scans == 3  # two scans to settle, one after the batch to find what it left
    assert rig.clock.time == _INTERVAL  # one interval between the two scans; none after the stop
    assert max(rig.clock.sleeps) <= 0.5


def test_watcher_stop_during_batch_finishes_the_batch_first(rig: _Rig) -> None:
    entry = rig.put("a.md")
    rig.during_batch = rig.watcher.stop  # Ctrl-C arrives while filing

    rig.watcher.run()

    assert rig.batches == [(entry,)]
    assert rig.events[-1].report is not None
    assert rig.watcher.stopping


def test_watcher_stop_while_waiting_ends_within_a_slice(rig: _Rig) -> None:
    rig.clock.on_sleep.append(rig.watcher.stop)  # the first sleep slice is interrupted

    rig.watcher.run()

    assert rig.scans == 1
    assert rig.clock.time == 0.5


def test_system_clock_moves_forward_and_sleeps() -> None:
    clock = SystemClock()
    before = clock.now()

    clock.sleep(0)

    assert clock.now() >= before


# endregion


# endregion
