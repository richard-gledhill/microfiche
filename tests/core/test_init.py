"""Tests for the ``core`` package's logging set-up in ``core/__init__.py``."""

import logging
import shutil
from pathlib import Path

from microfiche.core.filer import rollback_job
from microfiche.core.library.library import Library
from microfiche.core.organizer import run_sort
from microfiche.core.reclassify import run_reclassify

from microfiche import core

_MOCK_LIBRARY = Path(__file__).resolve().parents[1] / "mock_library"

# region Package logger


def test_core_logger_has_null_handler() -> None:
    # Without it a program that never configures logging gets Python's last-resort output: the
    # library's WARNING records printed to stderr. Only an application should decide where logs go.
    handlers = logging.getLogger(core.__name__).handlers

    assert any(isinstance(handler, logging.NullHandler) for handler in handlers)


# endregion


# region Root logger


def test_core_import_adds_no_handler_of_its_own_to_root() -> None:
    # pytest owns the root logger's other handlers, so look for the kinds core could have added: a plain
    # NullHandler (what the package logger gets), or a handler class from microfiche.core or from Rich.
    ours = [
        handler
        for handler in logging.getLogger().handlers
        if type(handler) is logging.NullHandler or type(handler).__module__.startswith(("microfiche.core", "rich"))
    ]

    assert ours == []


def test_core_run_leaves_root_logger_alone(tmp_path: Path) -> None:
    # Importing core did nothing to the root logger (above); this checks that using it does not either.
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    shutil.copytree(_MOCK_LIBRARY, tmp_path / "library")
    library = Library(tmp_path / "library")

    report = run_sort(library)
    run_reclassify(library)
    assert report.job is not None
    rollback_job(library, report.job.job_id)

    assert root.handlers == handlers
    assert root.level == level


# endregion
