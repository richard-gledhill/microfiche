"""Tests for the ``core`` package's logging set-up in ``core/__init__.py``."""

import logging

import core

# region Package logger


def test_core_logger_has_null_handler() -> None:
    # Without it a program that never configures logging gets Python's last-resort output: the
    # library's WARNING records printed to stderr. Only an application should decide where logs go.
    handlers = logging.getLogger(core.__name__).handlers

    assert any(isinstance(handler, logging.NullHandler) for handler in handlers)


# endregion
