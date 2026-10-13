"""Sets up logging for one CLI command: the console always, and the log file for a command that changes the library.

Only the CLI configures logging. ``core`` just emits records (``core/__init__.py`` adds a ``NullHandler`` to
its logger and nothing else), so where they go and how much is shown is decided here.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from microfiche.core.config import LoggingConfig
from microfiche.core.library.library import Library
from rich.console import Console
from rich.logging import RichHandler

# The loggers the handlers go on. Every record from ``microfiche.core.*`` and ``microfiche.cli.*`` reaches them, and nothing from other
# packages does (the AI SDKs' HTTP clients, for one), so a third party's chatter stays out of the log.
_LOGGER_NAMES = ("microfiche.core", "microfiche.cli")

# Pass as ``extra=FILE_ONLY`` to a log call whose message the user has already been told on screen: the record is
# written to the log file but kept off the console, so it is not shown twice.
_FILE_ONLY_KEY = "file_only"
FILE_ONLY: dict[str, bool] = {_FILE_ONLY_KEY: True}

# stderr, so piped output stays clean. The progress display shares this console, so log lines print above its bar.
stderr_console = Console(stderr=True)

# The handlers ``configure_logging`` added, so the next call can take off exactly those and no others.
_installed: list[logging.Handler] = []


def configure_logging(*, verbose: bool = False, quiet: bool = False, library: Library | None = None) -> None:
    """Set up logging for one command, replacing whatever an earlier call set up.

    The loggers pass every record on and each handler filters, so the console and the file can show different
    amounts. The console shows WARNING and above, INFO with ``verbose`` and only ERROR and above with ``quiet``.
    The file, when there is one, records at the library's ``[logging] level``, or DEBUG with ``verbose``.

    Args:
        verbose: Show more (``-v``). Ignored when ``quiet`` is also set, because quiet wins.
        quiet: Show errors only on the console (``-q``).
        library: The library whose ``.microfiche/`` folder holds the log file. Pass it only from a command that
            holds the run lock: the file is opened at the first record, so a command that passes none (a
            preview, a read-only command) writes no log file and never creates the state folder.
    """

    reset_logging()
    verbose = verbose and not quiet
    for name in _LOGGER_NAMES:
        logging.getLogger(name).setLevel(logging.DEBUG)

    console_handler = RichHandler(
        console=stderr_console,
        show_path=False,
        level=_console_level(verbose=verbose, quiet=quiet),
    )
    console_handler.addFilter(_ConsoleFilter())
    handlers: list[logging.Handler] = [console_handler]

    if library is not None:
        settings = library.config.logging
        file_handler = RotatingFileHandler(
            library.state_dir / settings.file,
            maxBytes=settings.max_bytes,
            backupCount=settings.backup_count,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setLevel(_file_level(settings, verbose=verbose))
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        handlers.append(file_handler)

    for handler in handlers:
        for name in _LOGGER_NAMES:
            logging.getLogger(name).addHandler(handler)
        _installed.append(handler)


def reset_logging() -> None:
    """Take off and close every handler ``configure_logging`` added, and put the loggers' levels back."""

    for handler in _installed:
        for name in _LOGGER_NAMES:
            logging.getLogger(name).removeHandler(handler)
        handler.close()
    _installed.clear()
    for name in _LOGGER_NAMES:
        logging.getLogger(name).setLevel(logging.NOTSET)


def _console_level(*, verbose: bool, quiet: bool) -> int:
    """The console's threshold: ERROR with ``quiet`` (which wins over ``verbose``), INFO with ``verbose``, else WARNING."""

    if quiet:
        return logging.ERROR
    return logging.INFO if verbose else logging.WARNING


def _file_level(settings: LoggingConfig, *, verbose: bool) -> int:
    """The log file's threshold: DEBUG with ``verbose``, else the level named in ``[logging] level``."""

    return logging.DEBUG if verbose else logging.getLevelNamesMapping()[settings.level]


class _ConsoleFilter(logging.Filter):
    """Decides, record by record, whether the console shows it. The log file has no such filter."""

    def filter(self, record: logging.LogRecord) -> bool:
        # ``extra=FILE_ONLY`` made the marker an attribute of the record; most records have none, hence the default.
        return not getattr(record, _FILE_ONLY_KEY, False)
