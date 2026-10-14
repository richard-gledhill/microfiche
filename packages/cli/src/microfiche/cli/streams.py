"""How microfiche writes to the screen: as UTF-8, and without a reader that went away aborting the command.

Both problems come from stdout and stderr not being a console. When output goes to a pipe, a file or a pseudo-terminal
such as Git Bash's, Python on Windows picks the legacy code page (cp1252) for text, so the em dash in a message becomes
a byte only a cp1252 reader understands and shows as a block. And when the reader stops early (``microfiche sort | head``),
the next write fails with ``EPIPE`` on Linux but ``EINVAL`` on Windows, which Rich does not recognise as a closed pipe, so
the command ends in a traceback after it has already done its work.
"""

from __future__ import annotations

import errno
import io
import os
import sys
from typing import Any

# What a write to a pipe with no reader fails with: EPIPE where the OS says so, EINVAL on Windows.
_READER_GONE = frozenset({errno.EPIPE, errno.EINVAL})


# region Public API


def prepare_output_streams() -> None:
    """Make stdout and stderr write UTF-8, and survive a reader that goes away.

    Call it once, before anything is printed. A stream that is a terminal is only given the encoding: it has no pipe to
    lose. Anything that is not a text stream (it has no ``reconfigure``) is left as it is.
    """

    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        _use_utf8(stream)
        if not _is_terminal(stream):
            setattr(sys, name, _ToleratesReaderGone(stream))


# endregion


# region Helpers


def _use_utf8(stream: object) -> None:
    """Write UTF-8 to ``stream``, replacing what it cannot hold (a file name with undecodable bytes, say) not raising."""

    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


def _is_terminal(stream: object) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(isatty()) if callable(isatty) else False


class _ToleratesReaderGone:
    """A stream that drops its output, once, when the reader at the other end has gone, and raises nothing else.

    Writing to a closed pipe is not a failure of the command: whatever it was asked to do is already done and recorded
    before it reports. So the first failed write or flush hands the OS-level stream to the null device (so the flush
    Python does at exit succeeds too) and every later write is accepted and discarded. A different error, such as a full
    disk or a permission problem, is still raised.
    """

    def __init__(self, stream: Any) -> None:
        self._stream = stream
        self._gone = False

    def write(self, text: str) -> int:
        if self._gone:
            return len(text)
        try:
            return int(self._stream.write(text))
        except OSError as err:
            self._lose(err)
            return len(text)

    def flush(self) -> None:
        if self._gone:
            return
        try:
            self._stream.flush()
        except OSError as err:
            self._lose(err)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)  # encoding, isatty, fileno... : everything else is the real stream's

    def _lose(self, err: OSError) -> None:
        if err.errno not in _READER_GONE:
            raise err
        self._gone = True
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            try:
                os.dup2(devnull, self._stream.fileno())
            finally:
                os.close(devnull)
        except (OSError, ValueError, io.UnsupportedOperation):
            pass  # not backed by a file descriptor (a test double), or already closed: dropping output is enough


# endregion
