"""Shows a progress bar on stderr while a long classification run works through its units.

``core`` reports how far it has got by calling ``progress(done, total)`` and knows nothing about how that is shown.
This module turns those calls into a Rich bar, on the same stderr console as the log lines, so a log line prints
above the bar instead of tearing it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from microfiche.cli.logging import stderr_console
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn

# A run with at least this many units gets a bar even without the AI. A shorter run is over before a bar is worth
# drawing. This is a display choice, not a setting.
_MANY_UNITS = 20


def should_show_progress(*, total: int, quiet: bool, ai: bool, is_terminal: bool) -> bool:
    """Whether a run of ``total`` units should get a progress bar.

    Args:
        total: How many units the run will classify.
        quiet: ``-q`` was given.
        ai: The AI fallback is in use, so a unit can take seconds.
        is_terminal: Whether the console is a real terminal. Output that is piped or redirected must stay clean.

    Returns:
        ``True`` to draw the bar.
    """

    # A bar needs a person to see it, must not defy -q, and needs something to count. Then it earns its place if the
    # run is long enough to take a while, or short but slow because each unit waits on the AI.
    return is_terminal and not quiet and total > 0 and (total >= _MANY_UNITS or ai)


@contextmanager
def progress_bar(*, quiet: bool, ai: bool, console: Console = stderr_console) -> Iterator[Callable[[int, int], None]]:
    """Give the caller a ``progress(done, total)`` callback that draws a bar when one is worth drawing.

    Whether to draw is decided once, from the first call, because that is when the number of units is known. The
    bar is removed from the screen when it finishes, and a bar that was drawn is stopped on the way out however the
    block ends.

    Args:
        quiet: ``-q`` was given.
        ai: The AI fallback is in use.
        console: Where to draw. The stderr console by default, which log lines share.

    Yields:
        The callback to hand to ``run_sort`` or ``run_reclassify``.
    """

    progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )
    task: TaskID | None = None
    decided = False

    def on_progress(done: int, total: int) -> None:
        nonlocal task, decided
        if not decided:
            decided = True
            if should_show_progress(total=total, quiet=quiet, ai=ai, is_terminal=console.is_terminal):
                progress.start()
                task = progress.add_task("Classifying", total=total)
        if task is not None:
            progress.update(task, completed=done)

    try:
        yield on_progress
    finally:
        # Only a bar that was started: on a console that is not a terminal, Rich's stop() prints a blank line even
        # for a bar that never ran, which would put a stray line into piped output.
        if task is not None:
            progress.stop()
