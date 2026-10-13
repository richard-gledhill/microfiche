"""Turns an exception into one short line a person can read."""

from __future__ import annotations

_MAX_CHARS = 200


def describe_error(err: BaseException) -> str:
    """``ExceptionType: first line of its message``, capped so one failure can't flood the output.

    Args:
        err: The exception to describe.

    Returns:
        A single line of at most 200 characters.
    """

    lines = str(err).splitlines()
    text = f"{type(err).__name__}: {lines[0]}" if lines else type(err).__name__
    return text if len(text) <= _MAX_CHARS else text[: _MAX_CHARS - 1] + "…"
