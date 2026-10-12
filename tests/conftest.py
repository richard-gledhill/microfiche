"""Fixtures shared across the test suite."""

import ctypes
import multiprocessing
import sys
from collections.abc import Callable, Iterator
from ctypes import wintypes
from pathlib import Path

import pytest

LinkMaker = Callable[[Path, Path], None]


@pytest.fixture
def make_symlink() -> LinkMaker:
    """Make ``link`` a symbolic link to ``target``; skips the test where the OS won't allow it.

    Windows only lets an administrator, or a user with Developer Mode on, create symbolic links.
    """

    def make(link: Path, target: Path) -> None:
        try:
            link.symlink_to(target, target_is_directory=target.is_dir())
        except (OSError, NotImplementedError):
            pytest.skip("this system does not allow creating symbolic links")

    return make


@pytest.fixture
def make_junction() -> LinkMaker:
    """Make ``link`` a Windows junction to the folder ``target``; skips the test on other systems."""

    def make(link: Path, target: Path) -> None:
        if sys.platform != "win32":
            pytest.skip("junctions only exist on Windows")
        import _winapi  # Windows only; this is how CPython's own tests make a junction

        _winapi.CreateJunction(str(target), str(link))

    return make


@pytest.fixture
def hold_open() -> Iterator[Callable[[Path], None]]:
    """Open a file the way Word does, until the test ends; skips the test on other systems.

    Word opens a document for reading and writing and lets other programs read it, but not rename or
    delete it. ``CreateFileW`` with ``FILE_SHARE_READ`` and no ``FILE_SHARE_DELETE`` is that sharing mode.
    """

    if sys.platform != "win32":
        pytest.skip("only Windows refuses to rename a file another program has open")
    generic_read, generic_write, file_share_read, open_existing = 0x80000000, 0x40000000, 0x1, 3
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    handles: list[int] = []

    def hold(path: Path) -> None:
        handle = kernel32.CreateFileW(
            str(path), generic_read | generic_write, file_share_read, None, open_existing, 0, None
        )
        if handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        handles.append(handle)

    yield hold
    for handle in handles:
        kernel32.CloseHandle(handle)


def _exit_at_once() -> None:
    """A process that does nothing and ends (it must be importable by name, for the spawned process)."""


@pytest.fixture
def dead_pid() -> int:
    """The id of a process that has already ended, for a lock left behind by a run that died."""

    process = multiprocessing.get_context("spawn").Process(target=_exit_at_once)
    process.start()
    process.join()
    assert process.pid is not None
    return process.pid
