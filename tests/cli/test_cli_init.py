"""Tests for `microfiche init`, and for the commands that now need a config to run."""

import json
import shutil
from pathlib import Path

import pytest
from microfiche.cli.app import app
from microfiche.core.config import CONFIG_FILENAME, load_config, packaged_defaults_text
from microfiche.core.library.library import Library
from microfiche.core.library.library_file import LIBRARY_FILENAME
from microfiche.core.runlock import run_lock
from typer.testing import CliRunner, Result

# region Test helpers


runner = CliRunner()

_MOCK_LIBRARY = Path(__file__).resolve().parents[1] / "mock_library"
_CUSTOM = """\
# My library's settings.
[classification]
# Stricter than the default.
confidence_threshold = 0.8  # chosen after a bad week
"""
# Enter at each of the six common settings.
_KEEP_COMMON = "\n" * 6


def _library(tmp_path: Path, config: str | None = _CUSTOM) -> Path:
    """A copy of the mock library, its config replaced by ``config`` (or removed with its state folder for ``None``)."""

    library = tmp_path / "library"
    shutil.copytree(_MOCK_LIBRARY, library)
    if config is None:
        shutil.rmtree(library / ".microfiche")
    else:
        (library / ".microfiche" / CONFIG_FILENAME).write_bytes(config.encode("utf-8"))
    return library


def _init(
    library: Path, answers: str | None = None, *, terminal: bool = True, monkeypatch: pytest.MonkeyPatch
) -> Result:
    monkeypatch.setattr("microfiche.cli.commands.stdin_is_terminal", lambda: terminal)
    return runner.invoke(app, ["init", "--library", str(library)], input=answers)


def _config(library: Path) -> bytes:
    return (library / ".microfiche" / CONFIG_FILENAME).read_bytes()


def _backup(library: Path) -> Path:
    return library / ".microfiche" / f"{CONFIG_FILENAME}.bak"


def _text(output: str) -> str:
    return " ".join(output.split())


# endregion


# region init: no install


@pytest.mark.parametrize("terminal", [True, False])
def test_init_no_install_writes_defaults_without_asking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, terminal: bool
) -> None:
    library = _library(tmp_path, None)
    shutil.rmtree(library / "_sorting")

    result = _init(library, "", terminal=terminal, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert _config(library).decode("utf-8") == packaged_defaults_text()
    groups = json.loads((library / ".microfiche" / LIBRARY_FILENAME).read_text(encoding="utf-8"))["groups"]
    assert [group["name"] for group in groups] == ["Project Phoenix"]
    assert (library / "_sorting").is_dir()
    assert "?" not in result.output  # nothing was asked
    shown = _text(result.output)
    assert "Wrote the default configuration" in shown
    assert "Created the inbox" in shown


def test_init_no_install_then_sort_dry_run_runs_quietly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path, None)
    _init(library, terminal=False, monkeypatch=monkeypatch)

    result = runner.invoke(app, ["sort", "--library", str(library), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "init" not in result.output
    assert "warning" not in result.output.lower()


def test_init_partial_install_library_file_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    (library / ".microfiche" / CONFIG_FILENAME).unlink()
    library_file = (library / ".microfiche" / LIBRARY_FILENAME).read_bytes()

    result = _init(library, terminal=False, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert (library / ".microfiche" / LIBRARY_FILENAME).read_bytes() == library_file
    assert "already lists every folder" in result.output


def test_init_no_install_lock_held_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path, None)

    with run_lock(Library(library), "sort"):
        result = _init(library, terminal=False, monkeypatch=monkeypatch)

    assert result.exit_code == 1
    assert not (library / ".microfiche" / CONFIG_FILENAME).exists()


# endregion


# region init: valid config


def test_init_valid_no_walk_through_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    (library / ".microfiche" / LIBRARY_FILENAME).unlink()

    result = _init(library, "n\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "The configuration is valid" in result.output
    assert _config(library) == _CUSTOM.encode()
    assert (library / ".microfiche" / LIBRARY_FILENAME).is_file()  # the partial install is completed


def test_init_valid_enter_everywhere_byte_identical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path, _CUSTOM.replace("\n", "\r\n"))

    result = _init(library, "y\n" + _KEEP_COMMON + "n\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "Nothing changed" in result.output
    assert _config(library) == _CUSTOM.replace("\n", "\r\n").encode()
    assert not _backup(library).exists()


def test_init_valid_change_one_setting_rewrites_that_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)

    result = _init(library, "y\n0.9\n" + "\n" * 5 + "n\ny\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "classification.confidence_threshold: 0.8 -> 0.9" in result.output
    assert _config(library) == _CUSTOM.replace("0.8  #", "0.9  #").encode()
    assert _backup(library).read_bytes() == _CUSTOM.encode()
    assert f"{CONFIG_FILENAME}.bak" in result.output
    shown = runner.invoke(app, ["config", "--library", str(library)])
    assert "0.9" in shown.output


def test_init_valid_bad_value_asked_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)

    result = _init(library, "y\n1.5\n0.9\n" + "\n" * 5 + "n\ny\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "less than or equal to 1" in result.output
    assert load_config(library / ".microfiche").classification.confidence_threshold == 0.9


def test_init_valid_other_settings_section_skippable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    # all others: yes; [classification] no, [ai] no, [sorting] yes (file_in_empty_groups kept, ignore), [parsing],
    # [logging], [exclusions], [naming_rules] no; then write: yes.
    answers = "y\n" + _KEEP_COMMON + "y\n" + "n\nn\ny\n\n*.bak, ~$*\n" + "n\n" * 4 + "y\n"

    result = _init(library, answers, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "[naming_rules]" in result.output
    assert load_config(library / ".microfiche").sorting.ignore == ["*.bak", "~$*"]
    assert "timeout" not in result.output  # [ai] was skipped


def test_init_valid_write_declined_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)

    result = _init(library, "y\n0.9\n" + "\n" * 5 + "n\nn\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "Nothing was written" in result.output
    assert _config(library) == _CUSTOM.encode()


def test_init_valid_existing_backup_kept_if_declined(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    _backup(library).write_bytes(b"older")

    result = _init(library, "y\n0.9\n" + "\n" * 5 + "n\ny\nn\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "Nothing was written" in result.output
    assert _config(library) == _CUSTOM.encode()
    assert _backup(library).read_bytes() == b"older"


def test_init_valid_existing_backup_replaced_if_agreed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    _backup(library).write_bytes(b"older")

    result = _init(library, "y\n0.9\n" + "\n" * 5 + "n\ny\ny\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert _backup(library).read_bytes() == _CUSTOM.encode()


def test_init_valid_interrupted_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)

    result = _init(library, "y\n0.9\n", monkeypatch=monkeypatch)  # input ends, as Ctrl-C would

    assert result.exit_code == 1
    assert _config(library) == _CUSTOM.encode()


def test_init_valid_no_terminal_reports_and_syncs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    (library / ".microfiche" / LIBRARY_FILENAME).unlink()

    result = _init(library, terminal=False, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "The configuration is valid" in result.output
    assert "Project Phoenix" in (library / ".microfiche" / LIBRARY_FILENAME).read_text(encoding="utf-8")


def test_init_valid_inbox_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    shutil.rmtree(library / "_sorting")

    result = _init(library, terminal=False, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert (library / "_sorting").is_dir()


# endregion


# region init: invalid config


_BROKEN = (
    "# Mine.\n[classification]\nconfidence_threshold = 0.8\nfuzzy_group_threshold = 500\n\n[classifcation]\nx = 1\n"
)


def test_init_invalid_revert_only_invalid_keeps_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path, _BROKEN)

    result = _init(library, "i\nn\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    shown = _text(result.output)
    assert "classification.fuzzy_group_threshold" in shown
    assert "classifcation: unknown section" in shown
    config = load_config(library / ".microfiche")
    assert config.classification.confidence_threshold == 0.8
    assert config.classification.fuzzy_group_threshold == 85
    assert _backup(library).read_bytes() == _BROKEN.encode()
    assert "# Mine." in _config(library).decode("utf-8")


def test_init_invalid_revert_all_restores_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path, _BROKEN)

    result = _init(library, "a\nn\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert _config(library).decode("utf-8") == packaged_defaults_text()
    assert _backup(library).read_bytes() == _BROKEN.encode()


def test_init_invalid_then_walk_through_offered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path, _BROKEN)

    # The second write does not ask about the backup the first one made, and keeps it.
    result = _init(library, "i\ny\n0.9\n" + "\n" * 5 + "n\ny\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert load_config(library / ".microfiche").classification.confidence_threshold == 0.9
    assert _backup(library).read_bytes() == _BROKEN.encode()
    assert "Not writing a log file" not in result.output


def test_init_invalid_leave_exits_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path, _BROKEN)

    result = _init(library, "l\n", monkeypatch=monkeypatch)

    assert result.exit_code == 1
    assert _config(library) == _BROKEN.encode()
    assert not _backup(library).exists()


def test_init_invalid_no_terminal_exits_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path, _BROKEN)

    result = _init(library, terminal=False, monkeypatch=monkeypatch)

    assert result.exit_code == 1
    assert "in a terminal" in _text(result.output)
    assert _config(library) == _BROKEN.encode()


def test_init_not_toml_only_revert_all_offered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path, "[classification\n")

    result = _init(library, "i\na\nn\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "(i)" not in result.output
    assert "Please answer one of: a, l" in result.output
    assert _config(library).decode("utf-8") == packaged_defaults_text()


# endregion


# region init: library file


def test_init_invalid_library_file_rebuilt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    (library / ".microfiche" / LIBRARY_FILENAME).write_text("{not json", encoding="utf-8")

    result = _init(library, "n\ny\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "Library file error" in result.output
    assert (library / ".microfiche" / f"{LIBRARY_FILENAME}.bak").read_text(encoding="utf-8") == "{not json"
    _ = Library(library).library_file  # loads, so it is valid


def test_init_invalid_library_file_left(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    (library / ".microfiche" / LIBRARY_FILENAME).write_text("{not json", encoding="utf-8")

    result = _init(library, "n\nn\n", monkeypatch=monkeypatch)

    assert result.exit_code == 1
    assert (library / ".microfiche" / LIBRARY_FILENAME).read_text(encoding="utf-8") == "{not json"


def test_init_invalid_library_file_no_terminal_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    (library / ".microfiche" / LIBRARY_FILENAME).write_text("{not json", encoding="utf-8")

    result = _init(library, terminal=False, monkeypatch=monkeypatch)

    assert result.exit_code == 1
    assert (library / ".microfiche" / LIBRARY_FILENAME).read_text(encoding="utf-8") == "{not json"


# endregion


# region Commands that need a config


@pytest.mark.parametrize("command", [["sort"], ["sort", "--dry-run"], ["reclassify"], ["propose-categories"]])
def test_command_no_config_stops_and_names_init(tmp_path: Path, command: list[str]) -> None:
    library = _library(tmp_path, None)

    result = runner.invoke(app, [*command, "--library", str(library)])

    assert result.exit_code == 1
    assert "microfiche init" in _text(result.output)
    assert not (library / ".microfiche").exists()


def test_command_invalid_config_suggests_init(tmp_path: Path) -> None:
    library = _library(tmp_path, _BROKEN)

    result = runner.invoke(app, ["config", "--library", str(library)])

    assert result.exit_code == 1
    assert "microfiche init" in _text(result.output)


# endregion


# region init: testing the AI connection

# The six common settings: threshold, depth, inbox, keep_folders, provider, then the model.
_SET_MODEL = "y\n" + "\n" * 5 + "llama3\n" + "n\n" + "y\n"  # walk through, set the model, skip the rest, write


class _Answers:
    """A stand-in provider that answers whatever it is asked."""

    def complete(self, prompt: str) -> str:
        return "OK"


class _Down:
    """A stand-in provider whose server is down."""

    _error = ConnectionError("connection refused")

    def complete(self, prompt: str) -> str:
        raise self._error


def test_init_ai_setting_changed_offers_connection_test_default_no(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _library(tmp_path)
    calls: list[object] = []
    monkeypatch.setattr("microfiche.cli.commands.check_ai", lambda *args: calls.append(args))

    result = _init(library, _SET_MODEL + "\n", monkeypatch=monkeypatch)  # Enter: the default, no

    assert result.exit_code == 0, result.output
    assert "Test the AI connection?" in result.output
    assert calls == []


def test_init_ai_setting_changed_test_yes_reports_the_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    monkeypatch.setattr("microfiche.core.ai.check.build_provider", lambda config: _Answers())

    result = _init(library, _SET_MODEL + "y\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "ollama llama3 answered in" in _text(result.output)


def test_init_ai_test_fails_init_still_succeeds_with_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _library(tmp_path)
    monkeypatch.setattr("microfiche.core.ai.check.build_provider", lambda config: _Down())

    result = _init(library, _SET_MODEL + "y\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output  # the config is already saved
    assert "connection refused" in _text(result.output)
    assert load_config(library / ".microfiche").ai.model == "llama3"


def test_init_ai_test_empty_model_says_so_instead_of_failing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)

    # Change only the timeout, so the model stays empty: six common settings kept, the other sections:
    # [classification] no, [ai] yes (host kept, timeout 30, three kept), the five after it no; write yes; test yes.
    answers = "y\n" + "\n" * 6 + "y\n" + "n\ny\n" + "\n" + "30\n" + "\n" * 3 + "n\n" * 5 + "y\ny\n"
    result = _init(library, answers, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "[ai] model is empty" in _text(result.output)


def test_init_no_ai_change_does_not_offer_the_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)

    result = _init(library, "y\n0.9\n" + "\n" * 5 + "n\ny\n", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "Test the AI connection?" not in result.output


def test_init_no_terminal_never_offers_the_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)

    result = _init(library, terminal=False, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "Test the AI connection?" not in result.output


# endregion
