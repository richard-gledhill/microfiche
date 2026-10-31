"""Tests for `microfiche watch`, driven by a watcher that has a fast clock and stops itself after a few scans."""

import json
import shutil
import signal
from pathlib import Path
from typing import Any, ClassVar

import pytest
from microfiche.cli import commands as cli_commands
from microfiche.cli.app import app
from microfiche.core.config import AIConfig
from microfiche.core.library.library import Library
from microfiche.core.runlock import run_lock
from microfiche.core.watcher import Watcher
from typer.testing import CliRunner

# region Test helpers

runner = CliRunner()
_MOCK_LIBRARY = Path(__file__).resolve().parents[1] / "mock_library"
_PHOENIX_NOTE = "PhoenixArchitectureNotes.md"  # files confidently
_SOLAR_NOTE = "SolarConstructionNotes.md"  # goes to review


class _FastClock:
    def __init__(self) -> None:
        self.time = 0.0

    def now(self) -> float:
        return self.time

    def sleep(self, seconds: float) -> None:
        self.time += seconds


class _ShortWatch(Watcher):
    """The real watcher, on a clock that never waits, that stops itself after ``scans`` scans."""

    scans: ClassVar[int] = 3
    made: ClassVar[list["_ShortWatch"]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, clock=_FastClock(), **kwargs)
        self.interval = kwargs["interval"]
        self.count = 0
        self.made.append(self)

    def step(self) -> Any:
        batch = super().step()
        self.count += 1
        if self.count >= self.scans:
            self.stop()
        return batch


@pytest.fixture(autouse=True)
def short_watch(monkeypatch: pytest.MonkeyPatch) -> None:
    _ShortWatch.scans = 3
    _ShortWatch.made = []
    monkeypatch.setattr(cli_commands, "Watcher", _ShortWatch)


def _library(tmp_path: Path) -> Path:
    library = tmp_path / "library"
    shutil.copytree(_MOCK_LIBRARY, library)
    shutil.rmtree(library / "_sorting" / "phoenix-weekly-pack")
    return library


def _watch(library: Path, *extra: str) -> Any:
    return runner.invoke(app, ["watch", "--library", str(library), *extra])


def _append_config(library: Path, text: str) -> None:
    config = library / ".microfiche" / "microfiche-config.toml"
    config.write_text(config.read_text(encoding="utf-8") + "\n" + text, encoding="utf-8")


# endregion


# region Public API


def test_watch_files_settled_document_and_prints_one_summary_line(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = _watch(library)

    assert result.exit_code == 0, result.stdout
    output = " ".join(result.stdout.split())
    assert "Filed 1, 1 for review, 0 duplicate(s); undo with `rollback --job-id" in output
    assert output.count("Filed 1") == 1
    assert not (library / "_sorting" / _PHOENIX_NOTE).exists()
    assert (library / "_sorting" / _SOLAR_NOTE).exists()


def test_watch_batch_is_one_job_that_rollback_undoes(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _watch(library)

    result = runner.invoke(app, ["rollback", "--library", str(library), "--last"])

    assert result.exit_code == 0, result.stdout
    assert (library / "_sorting" / _PHOENIX_NOTE).exists()


def test_watch_first_scan_alone_files_nothing(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _ShortWatch.scans = 1

    result = _watch(library)

    assert result.exit_code == 0, result.stdout
    assert (library / "_sorting" / _PHOENIX_NOTE).exists()


def test_watch_held_document_not_reviewed_again(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _ShortWatch.scans = 6

    result = _watch(library)

    assert " ".join(result.stdout.split()).count("1 for review") == 1


def test_watch_interval_defaults_to_the_config_and_flag_overrides(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _append_config(library, "[watch]\ninterval_seconds = 120\n")

    _watch(library)
    _watch(library, "--interval", "5")

    assert [watcher.interval for watcher in _ShortWatch.made] == [120, 5]


def test_watch_packaged_default_interval_is_an_hour(tmp_path: Path) -> None:
    _watch(_library(tmp_path))

    assert _ShortWatch.made[0].interval == 3600


@pytest.mark.parametrize("value", ["0", "-5"])
def test_watch_interval_not_positive_fails(tmp_path: Path, value: str) -> None:
    result = _watch(_library(tmp_path), "--interval", value)

    assert result.exit_code == 1
    assert "--interval must be greater than 0" in result.stdout


def test_watch_no_config_stops_and_names_init(tmp_path: Path) -> None:
    library = tmp_path / "bare"
    library.mkdir()

    result = _watch(library)

    assert result.exit_code == 1
    assert "microfiche init" in result.stdout


def test_watch_json_prints_one_compact_sort_document_per_batch(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = _watch(library, "--json")

    assert result.exit_code == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 1
    document = json.loads(lines[0])
    assert document["command"] == "sort"
    assert [unit["path"] for unit in document["filed"]] == [f"_sorting/{_PHOENIX_NOTE}"]
    assert document["job_id"]
    assert "Filed 1" in " ".join(result.stderr.split())  # the summary goes to stderr


def test_watch_json_failed_batch_is_an_error_line_and_watching_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_commands, "run_sort", explode)
    _ShortWatch.scans = 4

    result = _watch(_library(tmp_path), "--json")

    assert result.exit_code == 0, result.stderr
    documents = [json.loads(line) for line in result.stdout.splitlines()]
    assert [document["command"] for document in documents] == ["error"] * 3  # scans 2-4 each retry
    assert "boom" in documents[0]["error"]
    assert "Batch failed" in result.stderr


def test_watch_lock_busy_past_timeout_skips_the_batch(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _append_config(library, "[watch]\nlock_timeout_seconds = 0\n")

    with run_lock(Library(library), "review"):
        result = _watch(library, "--json")

    assert result.exit_code == 0, result.stderr
    assert result.stdout == ""  # a skipped batch is not a sort document
    assert "Batch skipped" in " ".join(result.stderr.split())
    assert (library / "_sorting" / _PHOENIX_NOTE).exists()


def test_watch_quiet_prints_no_summary_line(tmp_path: Path) -> None:
    result = _watch(_library(tmp_path), "-q")

    assert result.exit_code == 0, result.stdout
    assert "Filed" not in result.stdout


def test_watch_use_ai_checks_the_ai_once_at_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    _append_config(library, '[ai]\nmodel = "mistral"\n')
    checked: list[AIConfig] = []

    class Provider:
        def complete(self, prompt: str) -> str:
            return "NONE"

    def check(settings: AIConfig, *, quiet: bool) -> Provider:
        checked.append(settings)
        return Provider()

    monkeypatch.setattr(cli_commands, "_checked_ai_provider", check)

    result = _watch(library, "--use-ai")

    assert result.exit_code == 0, result.stdout
    assert len(checked) == 1
    assert checked[0].model == "mistral"


def test_watch_without_use_ai_asks_no_ai(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        pytest.fail("no AI without --use-ai")

    monkeypatch.setattr(cli_commands, "_checked_ai_provider", refuse)

    assert _watch(_library(tmp_path)).exit_code == 0


def test_stop_on_interrupt_first_ctrl_c_stops_after_the_batch_and_second_interrupts() -> None:
    stopped: list[bool] = []

    class FakeWatcher:
        stopping = False

        def stop(self) -> None:
            self.stopping = True
            stopped.append(True)

    watcher = FakeWatcher()
    before = signal.getsignal(signal.SIGINT)

    with cli_commands._stop_on_interrupt(watcher):
        handler = signal.getsignal(signal.SIGINT)
        assert callable(handler)
        handler(signal.SIGINT, None)
        assert stopped == [True]
        with pytest.raises(KeyboardInterrupt):
            handler(signal.SIGINT, None)

    assert signal.getsignal(signal.SIGINT) == before


# endregion
