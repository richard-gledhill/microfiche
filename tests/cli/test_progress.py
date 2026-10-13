"""Tests for the CLI's progress bar."""

import io

import pytest
from microfiche.cli.progress import _MANY_UNITS, progress_bar, should_show_progress
from rich.console import Console

# region Test helpers


def _console(*, terminal: bool) -> tuple[Console, io.StringIO]:
    """A console that writes to a buffer, and either is or is not a real terminal."""

    buffer = io.StringIO()
    return Console(file=buffer, force_terminal=terminal, width=80), buffer


# endregion


# region should_show_progress


@pytest.mark.parametrize(
    ("total", "quiet", "ai", "is_terminal", "expected"),
    [
        pytest.param(_MANY_UNITS, False, False, True, True, id="many-units-on-a-terminal"),
        pytest.param(_MANY_UNITS - 1, False, False, True, False, id="one-short-of-many-without-ai"),
        pytest.param(3, False, True, True, True, id="few-units-but-ai-makes-each-slow"),
        pytest.param(0, False, True, True, False, id="nothing-to-do"),
        pytest.param(500, False, True, False, False, id="piped-output-stays-clean"),
        pytest.param(500, True, True, True, False, id="quiet-hides-it"),
    ],
)
def test_should_show_progress_rules(total: int, quiet: bool, ai: bool, is_terminal: bool, expected: bool) -> None:
    assert should_show_progress(total=total, quiet=quiet, ai=ai, is_terminal=is_terminal) is expected


# endregion


# region progress_bar


def test_progress_bar_draws_on_a_terminal_when_wanted() -> None:
    console, buffer = _console(terminal=True)

    with progress_bar(quiet=False, ai=True, console=console) as on_progress:
        on_progress(0, 5)
        on_progress(3, 5)
        on_progress(5, 5)

    assert "Classifying" in buffer.getvalue()


def test_progress_bar_draws_nothing_when_not_a_terminal() -> None:
    console, buffer = _console(terminal=False)

    with progress_bar(quiet=False, ai=True, console=console) as on_progress:
        on_progress(0, 500)
        on_progress(500, 500)

    assert buffer.getvalue() == ""


def test_progress_bar_draws_nothing_when_quiet() -> None:
    console, buffer = _console(terminal=True)

    with progress_bar(quiet=True, ai=True, console=console) as on_progress:
        on_progress(0, 500)

    assert buffer.getvalue() == ""


def test_progress_bar_decides_from_the_first_call_only() -> None:
    # The first call says how many units there are. A later, bigger total must not switch the bar on.
    console, buffer = _console(terminal=True)

    with progress_bar(quiet=False, ai=False, console=console) as on_progress:
        on_progress(0, 3)
        on_progress(1, 500)

    assert buffer.getvalue() == ""


def test_progress_bar_never_called_leaves_the_screen_alone() -> None:
    console, buffer = _console(terminal=True)

    with progress_bar(quiet=False, ai=True, console=console):
        pass

    assert buffer.getvalue() == ""


# endregion
