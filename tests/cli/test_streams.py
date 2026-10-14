"""Tests for the output streams: text is written as UTF-8, and a reader that goes away never aborts a command."""

import contextlib
import io
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from microfiche.cli.streams import prepare_output_streams

# region Test helpers


def _use(monkeypatch: pytest.MonkeyPatch, stdout: object, stderr: object) -> None:
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)


def _legacy_stream() -> tuple[io.TextIOWrapper, io.BytesIO]:
    """A text stream with the encoding Windows gives a pipe or a pseudo-terminal, over bytes we can read back."""

    raw = io.BytesIO()
    return io.TextIOWrapper(raw, encoding="cp1252", newline="\n", write_through=True), raw


@contextmanager
def _pipe_with_no_reader() -> Iterator[io.TextIOWrapper]:
    """A text stream on a pipe whose reading end is already closed, as when the output is piped to ``head``."""

    read_fd, write_fd = os.pipe()
    os.close(read_fd)
    stream = os.fdopen(write_fd, "w", encoding="utf-8")
    try:
        yield stream
    finally:
        with contextlib.suppress(OSError):  # closing flushes what was buffered, into a pipe nobody is reading
            stream.close()


# endregion


# region prepare_output_streams: encoding


def test_prepare_output_streams_legacy_code_page_text_written_as_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout, out_raw = _legacy_stream()
    stderr, err_raw = _legacy_stream()

    _use(monkeypatch, stdout, stderr)
    prepare_output_streams()
    print("empty value: —", file=sys.stdout)
    print("a warning — with a dash", file=sys.stderr)
    sys.stdout.flush()
    sys.stderr.flush()

    assert out_raw.getvalue() == "empty value: —\n".encode()  # not b"\x97", which only a cp1252 reader understands
    assert err_raw.getvalue() == "a warning — with a dash\n".encode()


def test_prepare_output_streams_text_the_encoding_cannot_hold_is_replaced_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout, out_raw = _legacy_stream()

    _use(monkeypatch, stdout, _legacy_stream()[0])
    prepare_output_streams()
    print("lone surrogate from an undecodable file name: \udcff", file=sys.stdout)
    sys.stdout.flush()

    assert out_raw.getvalue().startswith(b"lone surrogate from an undecodable file name: ")


def test_prepare_output_streams_stream_without_reconfigure_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    class Plain:
        encoding = "cp1252"

        def isatty(self) -> bool:
            return True

    plain = Plain()

    _use(monkeypatch, plain, plain)
    prepare_output_streams()

    assert sys.stdout is plain  # something that is not a text stream (a test double, say) is not touched


# endregion


# region prepare_output_streams: a reader that went away


def test_prepare_output_streams_closed_pipe_writes_and_flushes_do_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    with _pipe_with_no_reader() as pipe:
        _use(monkeypatch, pipe, io.StringIO())
        prepare_output_streams()

        for _ in range(50):
            print("x" * 4096, file=sys.stdout)  # far more than a pipe buffer holds, so the failure is certain
        sys.stdout.flush()

        assert True  # reaching here is the point: no OSError (EPIPE, or EINVAL on Windows) escaped


def test_prepare_output_streams_closed_pipe_later_output_is_dropped_quietly(monkeypatch: pytest.MonkeyPatch) -> None:
    with _pipe_with_no_reader() as pipe:
        _use(monkeypatch, pipe, io.StringIO())
        prepare_output_streams()
        for _ in range(50):
            print("x" * 4096, file=sys.stdout)

        written = sys.stdout.write("after the reader left")

        assert written == len("after the reader left")  # callers see a normal write


def test_prepare_output_streams_other_os_error_still_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    class Failing(io.StringIO):
        def write(self, text: str) -> int:
            raise PermissionError(13, "Permission denied")

    _use(monkeypatch, Failing(), io.StringIO())
    prepare_output_streams()

    with pytest.raises(PermissionError):
        sys.stdout.write("a real failure")  # only a vanished reader is tolerated, nothing else


def test_prepare_output_streams_terminal_not_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    terminal = Terminal()

    _use(monkeypatch, terminal, terminal)
    prepare_output_streams()

    assert sys.stdout is terminal  # a terminal has no pipe to close; Rich keeps its own handling of it


# endregion
