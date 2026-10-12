"""A lock that stops two microfiche runs from changing the same library at once.

``sort``, ``reclassify --apply`` and ``rollback`` each plan a batch of moves and then make them. A second
run starting in between could plan against a library that is about to change, and both would write the
ledger and audit log. So a run takes ``.microfiche/lock`` first and a second run refuses to start while
it is held. Commands that only read (a ``--dry-run`` preview, ``audit``, ``config``) take no lock.

The lock file records which process holds it. If that process is gone - the machine lost power, say - the
lock is stale and is cleared. A lock file that cannot be understood is treated as held, never cleared:
guessing wrong would let two runs through, and deleting one file is an easy fix for a person to make.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.library.library import Library
from core.utils.errors import describe_error

# region Constants and types

LOCK_FILENAME = "lock"

# Windows: ask to query a process without any right to change it; it fails with this code if access is denied.
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_ACCESS_DENIED = 5
_STILL_ACTIVE = 259


@dataclass(frozen=True)
class LockHolder:
    """Who holds the lock, as recorded in the lock file.

    Attributes:
        pid: The process id of the run.
        command: The command it is running, such as ``"sort"``.
        started: When it took the lock.
    """

    pid: int
    command: str
    started: datetime


# endregion


# region Errors


class RunLockError(RuntimeError):
    """A run could not take the lock. The message says why and what to do about it."""


class RunLockedError(RunLockError):
    """Another run holds the lock, or the lock file cannot be read to tell.

    Attributes:
        path: The lock file.
        holder: Who holds it, or ``None`` if the file could not be read.
    """

    def __init__(self, path: Path, holder: LockHolder | None) -> None:
        self.path = path
        self.holder = holder
        if holder is None:
            message = (
                f"The run lock {path} exists but cannot be read, so microfiche cannot tell whether another run "
                "is active. If none is, delete that file and try again."
            )
        else:
            message = (
                f"Another microfiche run is already in progress ({holder.command}, process {holder.pid}, started "
                f"{holder.started:%Y-%m-%d %H:%M:%S}). Wait for it to finish and try again. "
                f"If no run is active, delete {path} and try again."
            )
        super().__init__(message)


class LockUnavailableError(RunLockError):
    """The lock file could not be created (for example the state folder is read-only)."""

    def __init__(self, path: Path, error: OSError) -> None:
        self.path = path
        super().__init__(f"Could not create the run lock {path}: {describe_error(error)}")


# endregion


# region Public API


@contextmanager
def run_lock(library: Library, command: str) -> Iterator[LockHolder | None]:
    """Hold the library's run lock for the duration of the ``with`` block.

    The lock file is created atomically, so of two runs starting together exactly one gets it. It is
    removed when the block ends, including when the block raises. A lock left by a process that no
    longer exists is cleared and taken over.

    The lock is taken before the caller can set up logging, so it does not log that it cleared a stale
    lock; it says so to its caller, which can.

    Args:
        library: The library the run is changing. Its state folder is created if it does not exist yet.
        command: The command taking the lock, recorded so a refused run can say what is in progress.

    Yields:
        Who held the stale lock that was cleared to take this one (the run that died), or ``None`` if there
        was none. The lock is held until the block ends.

    Raises:
        RunLockedError: if another run holds the lock, or the lock file exists but cannot be read.
        LockUnavailableError: if the lock file cannot be created.
    """

    path = library.state_dir / LOCK_FILENAME
    cleared = _acquire(path, command)
    try:
        yield cleared
    finally:
        _release(path)


# endregion


# region Helpers


def _acquire(path: Path, command: str) -> LockHolder | None:
    """Create the lock file, clearing it first if it is stale.

    Returns:
        Who held the stale lock that was cleared, or ``None`` if the lock file was not there.
    """

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        raise LockUnavailableError(path, err) from err

    try:
        _create(path, command)
    except FileExistsError:
        return _take_over_if_stale(path, command)
    return None


def _take_over_if_stale(path: Path, command: str) -> LockHolder:
    """The lock file exists: clear it and take the lock if its holder is gone, otherwise refuse.

    Returns:
        The holder of the stale lock that was cleared.
    """

    holder = _read_holder(path)
    if holder is None or _process_alive(holder.pid):
        raise RunLockedError(path, holder)
    with contextlib.suppress(FileNotFoundError):  # another run may have cleared it already
        path.unlink()
    try:
        _create(path, command)
    except FileExistsError as err:  # someone else took it in the moment since we cleared it
        raise RunLockedError(path, _read_holder(path)) from err
    return holder


def _create(path: Path, command: str) -> None:
    """Atomically create the lock file holding this process's details.

    Raises:
        FileExistsError: if the lock file already exists.
        LockUnavailableError: if it cannot be created or written for another reason.
    """

    details = {
        "pid": os.getpid(),
        "command": command,
        "started": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise
    except OSError as err:
        raise LockUnavailableError(path, err) from err
    try:
        try:
            os.write(descriptor, json.dumps(details).encode("utf-8"))
        finally:
            os.close(descriptor)  # closed before any cleanup: Windows will not delete a file that is still open
    except OSError as err:
        with contextlib.suppress(OSError):
            path.unlink()
        raise LockUnavailableError(path, err) from err


def _release(path: Path) -> None:
    """Remove the lock file, but only if this process still owns it."""

    holder = _read_holder(path)
    if holder is not None and holder.pid == os.getpid():
        with contextlib.suppress(OSError):
            path.unlink()


def _read_holder(path: Path) -> LockHolder | None:
    """Who the lock file says holds the lock, or ``None`` if it is missing or cannot be understood."""

    try:
        details = json.loads(path.read_text(encoding="utf-8"))
        return LockHolder(
            pid=int(details["pid"]),
            command=str(details["command"]),
            started=datetime.fromisoformat(details["started"]),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _process_alive(pid: int) -> bool:
    """Whether a process with this id is running.

    On Windows this asks the operating system for the process. ``os.kill(pid, 0)``, the usual check on
    other systems, must not be used there: it does not test anything, it sends the process a Ctrl-C.
    """

    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _windows_process_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # it exists, but belongs to someone else
    return True


def _windows_process_alive(pid: int) -> bool:
    """Whether a process is running, asked of Windows directly (only called on Windows)."""

    if sys.platform != "win32":  # also tells mypy the rest is Windows-only, so it is not checked on other systems
        return False
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ctypes.get_last_error() == _ERROR_ACCESS_DENIED  # denied means it exists; anything else, it does not
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


# endregion
