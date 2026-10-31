"""The loop behind ``microfiche watch``: rescan the inbox and file what has stopped changing.

Every scan is a stat-only ``snapshot_inbox``: it never reads content, so a cloud-synced placeholder is not downloaded
by being looked at. An inbox entry is *stable* when its signature (size and modification time of what it holds) is the
same in two scans in a row. A batch runs when something is stable and the scan was quiet, nothing new or changed, so a
folder copied in is filed as one job after it has finished arriving. One interval is therefore the quiet period.

A unit the batch left for review (or as a duplicate) is not tried again until it changes or the config or the
library file changes, which is all that could change the answer.

The loop knows nothing about the clock, the screen or the lock: it takes a ``Clock``, the function that runs a
batch, and a function that reports one, so the tests drive it with fakes and never wait.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from microfiche.core.config import CONFIG_FILENAME
from microfiche.core.drift import DriftReport
from microfiche.core.library.library import Library
from microfiche.core.library.library_file import LIBRARY_FILENAME
from microfiche.core.organizer import SortReport
from microfiche.core.runlock import RunLockedError
from microfiche.core.scanner import InboxSnapshot, Signature, snapshot_inbox

_logger = logging.getLogger(__name__)

# region Constants and types

_SLICE_SECONDS = 0.5  # the longest single sleep, so a stop request is noticed within half a second


class Clock(Protocol):
    """Time, as the loop needs it. The real one is ``SystemClock``; the tests supply one that never waits."""

    def now(self) -> float:
        """Seconds on a clock that only moves forward."""
        ...

    def sleep(self, seconds: float) -> None:
        """Wait this long."""
        ...


class SystemClock:
    """The real clock."""

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass(frozen=True)
class WatchBatch:
    """What one attempt to file a batch came to. Exactly one of ``report``, ``skipped`` and ``error`` is set.

    Attributes:
        entries: The inbox entries the batch was for (empty for a scan that failed before finding any).
        library: The library as it was opened for this batch, for rendering the report.
        report: The sort that ran.
        drift: What the drift check found just before it.
        skipped: Why the batch did not run: another run held the lock past the timeout. It is tried again.
        error: Why the batch or the scan failed. The loop carries on and tries again at the next scan.
    """

    entries: tuple[Path, ...]
    library: Library | None = None
    report: SortReport | None = None
    drift: DriftReport | None = None
    skipped: str | None = None
    error: str | None = None


RunBatch = Callable[[Library, tuple[Path, ...]], tuple[SortReport, DriftReport]]

# endregion


# region Public API


class Watcher:
    """Polls a library's inbox and files each batch of settled units through ``run_batch``.

    Args:
        open_library: Opens the library afresh. Called every scan, so a changed config or library file is picked up.
        run_batch: Files the given inbox entries and returns the sort report and drift check. It takes the run lock
            and raises ``RunLockedError`` if it cannot, which skips the batch until the next scan.
        on_batch: Told about every batch that ran, was skipped or failed. Idle scans are not reported.
        interval: Seconds between scans.
        snapshot: Takes the stat-only snapshot of the inbox.
        clock: Time. Faked in the tests.
    """

    def __init__(
        self,
        open_library: Callable[[], Library],
        run_batch: RunBatch,
        on_batch: Callable[[WatchBatch], None],
        *,
        interval: float,
        snapshot: Callable[[Library], InboxSnapshot] = snapshot_inbox,
        clock: Clock | None = None,
    ) -> None:
        self._open_library = open_library
        self._run_batch = run_batch
        self._on_batch = on_batch
        self._interval = interval
        self._snapshot = snapshot
        self._clock = clock if clock is not None else SystemClock()
        self._stopping = False
        self._previous: InboxSnapshot | None = None
        self._held: dict[Path, Signature] = {}
        self._settings: tuple[tuple[int, int] | None, ...] | None = None

    @property
    def stopping(self) -> bool:
        """Whether a stop was asked for."""

        return self._stopping

    def stop(self) -> None:
        """Ask the loop to end. A batch in progress finishes first, so no job is left half-filed."""

        self._stopping = True

    def run(self) -> None:
        """Scan, file and wait until ``stop`` is called."""

        while not self._stopping:
            self.step()
            self._wait()

    def step(self) -> WatchBatch | None:
        """Scan once and file a batch if one is due.

        Returns:
            The batch (also passed to ``on_batch``), or ``None`` if nothing was due. A failure to open the library or
            scan is a batch with an ``error``, never an exception: an unattended run must outlive a bad moment.
        """

        try:
            return self._step()
        except Exception as err:  # keep watching whatever went wrong; the next scan tries again
            _logger.exception("watch: scan failed")
            return self._finish(WatchBatch(entries=(), error=f"{type(err).__name__}: {err}"))

    def _step(self) -> WatchBatch | None:
        library = self._open_library()
        current = self._snapshot(library)
        settings = _settings_stamp(library)
        if settings != self._settings:
            if self._held:
                _logger.info("watch: config or library file changed; held units will be tried again")
            self._held.clear()
            self._settings = settings
        previous, self._previous = self._previous, current
        self._held = {entry: sig for entry, sig in self._held.items() if current.get(entry) == sig}
        if previous is None:
            _logger.info("watch: first scan found %d entr(ies); filing waits for them to settle", len(current))
            return None
        changed = [entry for entry, sig in current.items() if previous.get(entry) != sig]
        if changed:
            _logger.info("watch: %d entr(ies) new or changed; waiting for a quiet scan", len(changed))
            return None
        ready = tuple(entry for entry in current if entry not in self._held)
        if not ready:
            _logger.info("watch: nothing to file (%d held for review)", len(self._held))
            return None
        return self._file(library, ready)

    def _file(self, library: Library, entries: tuple[Path, ...]) -> WatchBatch:
        try:
            report, drift = self._run_batch(library, entries)
        except RunLockedError as err:
            _logger.warning("watch: batch skipped, the run lock is busy: %s", err)
            return self._finish(WatchBatch(entries, library, skipped=str(err)))
        except Exception as err:  # keep watching; the same entries are tried again at the next scan
            _logger.exception("watch: batch failed")
            return self._finish(WatchBatch(entries, library, error=f"{type(err).__name__}: {err}"))
        self._remember_held(library, report)
        return self._finish(WatchBatch(entries, library, report, drift))

    def _remember_held(self, library: Library, report: SortReport) -> None:
        """Take a fresh look at the inbox after a batch, and mark what the batch left behind as held.

        The fresh look is also the baseline for the next scan, so what the batch itself changed (filed units gone,
        a folder with fewer files, the library file updated) does not count as new or changed.
        """

        after = self._snapshot(library)
        self._previous = after
        self._settings = _settings_stamp(library)
        left = {_entry_of(library, unit.source_path) for unit, _ in report.needs_review}
        left |= {_entry_of(library, duplicate.unit.source_path) for duplicate in report.duplicates}
        self._held = {entry: after[entry] for entry in left if entry in after}

    def _finish(self, batch: WatchBatch) -> WatchBatch:
        self._on_batch(batch)
        return batch

    def _wait(self) -> None:
        """Sleep one interval in short slices, so ``stop`` takes effect within a slice."""

        deadline = self._clock.now() + self._interval
        while not self._stopping:
            remaining = deadline - self._clock.now()
            if remaining <= 0:
                return
            self._clock.sleep(min(_SLICE_SECONDS, remaining))


# endregion


# region Helpers


def _entry_of(library: Library, source_path: Path) -> Path:
    """The inbox entry (file or folder directly in the inbox) that holds the unit at ``source_path``."""

    return library.inbox / source_path.relative_to(library.inbox).parts[0]


def _settings_stamp(library: Library) -> tuple[tuple[int, int] | None, ...]:
    """Size and modification time of the config and the library file (``None`` for one that is not there)."""

    stamp: list[tuple[int, int] | None] = []
    for name in (CONFIG_FILENAME, LIBRARY_FILENAME):
        try:
            info = (library.state_dir / name).stat()
        except OSError:
            stamp.append(None)
        else:
            stamp.append((info.st_size, info.st_mtime_ns))
    return tuple(stamp)


# endregion
