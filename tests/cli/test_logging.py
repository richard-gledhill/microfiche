"""Tests for the CLI's logging set-up."""

import logging
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from cli.logging import configure_logging, reset_logging
from core.library.library import Library

# region Test helpers


_MOCK_LIBRARY = Path(__file__).resolve().parents[1] / "mock_library"
_CORE = logging.getLogger("core.sample")
_CLI = logging.getLogger("cli.sample")
_LOG_NAME = "microfiche.log"


@pytest.fixture(autouse=True)
def _reset_logging_after_each_test() -> Iterator[None]:
    """Take the handlers off after each test, so one test's file handler cannot leak into the next."""

    yield
    reset_logging()


def _library(tmp_path: Path) -> Library:
    """A copy of the mock library, so a test can write into its ``.microfiche/`` folder."""

    root = tmp_path / "library"
    shutil.copytree(_MOCK_LIBRARY, root)
    return Library(root)


def _emit_every_level(logger: logging.Logger) -> None:
    logger.debug("a debug record")
    logger.info("an info record")
    logger.warning("a warning record")
    logger.error("an error record")


def _log_text(library: Library, name: str = _LOG_NAME) -> str:
    return (library.state_dir / name).read_text(encoding="utf-8")


# endregion


# region configure_logging


# region Console


def test_configure_logging_default_console_warning_and_above(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()

    _emit_every_level(_CORE)

    err = capsys.readouterr().err
    assert "a warning record" in err
    assert "an error record" in err
    assert "an info record" not in err
    assert "a debug record" not in err


def test_configure_logging_verbose_console_adds_info(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(verbose=True)

    _emit_every_level(_CORE)

    err = capsys.readouterr().err
    assert "an info record" in err
    assert "a debug record" not in err  # DEBUG goes to the file only


def test_configure_logging_quiet_console_errors_only(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(quiet=True)

    _emit_every_level(_CORE)

    err = capsys.readouterr().err
    assert "an error record" in err
    assert "a warning record" not in err


def test_configure_logging_quiet_and_verbose_quiet_wins(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(verbose=True, quiet=True)

    _emit_every_level(_CORE)

    err = capsys.readouterr().err
    assert "an error record" in err
    assert "an info record" not in err
    assert "a warning record" not in err


def test_configure_logging_cli_logger_reaches_console(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()

    _CLI.warning("from the cli package")

    assert "from the cli package" in capsys.readouterr().err


def test_configure_logging_other_package_not_shown(capsys: pytest.CaptureFixture[str]) -> None:
    # The handlers are on core and cli, not the root logger, so a third party's records stay out.
    configure_logging()

    logging.getLogger("httpx").warning("third party noise")

    assert "third party noise" not in capsys.readouterr().err


def test_configure_logging_twice_logs_each_record_once(capsys: pytest.CaptureFixture[str]) -> None:
    # A test suite (or a long-lived process) calls it again; handlers must be replaced, not piled up.
    configure_logging()
    configure_logging()

    _CORE.warning("a warning record")

    assert capsys.readouterr().err.count("a warning record") == 1


def test_configure_logging_records_still_reach_caplog(caplog: pytest.LogCaptureFixture) -> None:
    # Loggers must keep propagating to the root logger, where pytest's caplog listens.
    configure_logging()

    _CORE.warning("seen by caplog")

    assert "seen by caplog" in caplog.text


# endregion


# region File


def test_configure_logging_file_default_level_info(tmp_path: Path) -> None:
    library = _library(tmp_path)
    configure_logging(library=library)

    _emit_every_level(_CORE)

    text = _log_text(library)
    assert "an info record" in text
    assert "a warning record" in text
    assert "a debug record" not in text


def test_configure_logging_file_verbose_adds_debug(tmp_path: Path) -> None:
    library = _library(tmp_path)
    configure_logging(verbose=True, library=library)

    _emit_every_level(_CORE)

    assert "a debug record" in _log_text(library)


def test_configure_logging_file_quiet_leaves_file_level(tmp_path: Path) -> None:
    library = _library(tmp_path)
    configure_logging(quiet=True, library=library)

    _emit_every_level(_CORE)

    assert "an info record" in _log_text(library)


def test_configure_logging_file_quiet_and_verbose_no_debug(tmp_path: Path) -> None:
    # Quiet wins, so -v is ignored for the file as well.
    library = _library(tmp_path)
    configure_logging(verbose=True, quiet=True, library=library)

    _emit_every_level(_CORE)

    text = _log_text(library)
    assert "an info record" in text
    assert "a debug record" not in text


def test_configure_logging_file_uses_configured_name_and_level(tmp_path: Path) -> None:
    library = _library(tmp_path)
    library.config.logging.file = "run.log"
    library.config.logging.level = "WARNING"
    configure_logging(library=library)

    _emit_every_level(_CORE)

    text = _log_text(library, "run.log")
    assert "a warning record" in text
    assert "an info record" not in text


def test_configure_logging_file_rotates_at_max_bytes(tmp_path: Path) -> None:
    library = _library(tmp_path)
    library.config.logging.max_bytes = 200
    library.config.logging.backup_count = 1
    configure_logging(library=library)

    for number in range(20):
        _CORE.info("record number %d", number)

    assert (library.state_dir / f"{_LOG_NAME}.1").exists()


def test_configure_logging_file_written_as_utf8(tmp_path: Path) -> None:
    # The Windows default encoding would garble or reject this.
    library = _library(tmp_path)
    configure_logging(library=library)

    _CORE.warning("café ✓")

    assert "café ✓" in _log_text(library)


def test_configure_logging_file_not_created_before_first_record(tmp_path: Path) -> None:
    library = _library(tmp_path)

    configure_logging(library=library)

    assert not (library.state_dir / _LOG_NAME).exists()


def test_configure_logging_no_library_writes_no_file(tmp_path: Path) -> None:
    library = _library(tmp_path)
    configure_logging()

    _emit_every_level(_CORE)

    assert not (library.state_dir / _LOG_NAME).exists()


# endregion


# endregion


# region reset_logging


def test_reset_logging_removes_handlers_and_levels() -> None:
    configure_logging()

    reset_logging()

    for name in ("core", "cli"):
        logger = logging.getLogger(name)
        assert logger.level == logging.NOTSET
        assert [h for h in logger.handlers if not isinstance(h, logging.NullHandler)] == []


def test_reset_logging_keeps_core_null_handler() -> None:
    configure_logging()

    reset_logging()

    assert any(isinstance(h, logging.NullHandler) for h in logging.getLogger("core").handlers)


def test_reset_logging_closes_log_file(tmp_path: Path) -> None:
    # On Windows a file that is still open cannot be deleted.
    library = _library(tmp_path)
    configure_logging(library=library)
    _CORE.warning("a warning record")

    reset_logging()

    (library.state_dir / _LOG_NAME).unlink()


# endregion
