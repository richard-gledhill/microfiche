"""Tests for ``--json``: one versioned JSON document on stdout, and nothing else there."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from microfiche.cli.app import app
from microfiche.cli.json_output import (
    AuditOutput,
    ConfigOutput,
    ErrorOutput,
    ReclassifyOutput,
    ReviewQueueOutput,
    RollbackOutput,
    SortOutput,
    output_schemas,
)
from typer.testing import CliRunner

# region Test helpers


runner = CliRunner()
_MOCK_LIBRARY = Path(__file__).resolve().parents[1] / "mock_library"
_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
_TEXT = "Project Phoenix architecture decisions, including a distinctive phrase: zanzibar-kumquat."
_MISFILED = "Project Phoenix/03 Research/misfiled.md"


def _library(tmp_path: Path) -> Path:
    library = tmp_path / "library"
    shutil.copytree(_MOCK_LIBRARY, library)
    shutil.rmtree(library / "_sorting" / "phoenix-weekly-pack")
    return library


def _json(args: list[str], *, code: int = 0) -> Any:
    """Run the CLI with ``--json`` and parse stdout, which must be exactly one JSON document."""

    result = runner.invoke(app, [*args, "--json"])
    assert result.exit_code == code, (result.stdout, result.stderr)
    return json.loads(result.stdout)


# endregion

# region sort


def test_sort_json_dry_run_lists_every_inbox_unit_once_and_moves_nothing(tmp_path: Path) -> None:
    library = _library(tmp_path)
    inbox = sorted(path.name for path in (library / "_sorting").iterdir() if path.name != ".gitkeep")

    document = _json(["sort", "--library", str(library), "--dry-run"])

    output = SortOutput.model_validate(document)
    listed = [Path(entry.path).name for entry in (*output.filed, *output.needs_review, *output.duplicates)]
    assert sorted(listed) == inbox
    assert output.dry_run is True
    assert output.job_id is None
    assert document["version"] == 1
    assert sorted(path.name for path in (library / "_sorting").iterdir() if path.name != ".gitkeep") == inbox


def test_sort_json_real_run_gives_job_id_and_destinations(tmp_path: Path) -> None:
    library = _library(tmp_path)

    output = SortOutput.model_validate(_json(["sort", "--library", str(library)]))

    assert output.job_id is not None
    assert output.filed
    assert all(entry.destination for entry in output.filed)
    assert all((library / entry.destination).is_file() for entry in output.filed if entry.destination)


def test_sort_json_holds_no_document_text(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / "_sorting" / "extra.md").write_text(_TEXT, encoding="utf-8")

    result = runner.invoke(app, ["sort", "--library", str(library), "--dry-run", "--json"])

    assert "zanzibar-kumquat" not in result.stdout


def test_sort_json_stdout_is_the_document_even_with_verbose(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["sort", "--library", str(library), "--dry-run", "--json", "-v"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["command"] == "sort"


def test_sort_without_json_prints_for_a_person(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["sort", "--library", str(library), "--dry-run"])

    assert "Preview:" in result.stdout


def test_sort_json_failure_is_json_on_stdout_and_exits_non_zero(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    result = runner.invoke(app, ["sort", "--library", str(empty), "--json"])

    assert result.exit_code == 1
    assert "No configuration found" in ErrorOutput.model_validate_json(result.stdout).error


# endregion

# region rollback and audit


def test_rollback_json_reports_the_job(tmp_path: Path) -> None:
    library = _library(tmp_path)
    sorted_ = SortOutput.model_validate(_json(["sort", "--library", str(library)]))

    output = RollbackOutput.model_validate(_json(["rollback", "--library", str(library), "--last"]))

    assert output.job_id == sorted_.job_id
    assert output.moves_reverted == len(sorted_.filed)


def test_audit_json_parses_the_log(tmp_path: Path) -> None:
    library = _library(tmp_path)
    sorted_ = SortOutput.model_validate(_json(["sort", "--library", str(library)]))

    output = AuditOutput.model_validate(_json(["audit", "--library", str(library)]))

    assert {entry.job_id for entry in output.entries} == {sorted_.job_id}
    assert {entry.action for entry in output.entries} >= {"move"}
    assert output.unparsed == []


def test_audit_json_no_log_is_an_empty_list(tmp_path: Path) -> None:
    library = _library(tmp_path)

    output = AuditOutput.model_validate(_json(["audit", "--library", str(library)]))

    assert output.entries == []


# endregion

# region reclassify


def test_reclassify_json_proposes_without_moving_then_applies(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / _MISFILED).write_text(_TEXT, encoding="utf-8")

    preview = ReclassifyOutput.model_validate(_json(["reclassify", "--library", str(library)]))
    applied = ReclassifyOutput.model_validate(_json(["reclassify", "--library", str(library), "--apply"]))

    assert preview.dry_run is True
    assert preview.job_id is None
    assert [p.action for p in preview.proposals if p.path == _MISFILED] == ["move"]
    assert applied.dry_run is False
    assert applied.job_id is not None
    assert (library / "Project Phoenix/02 Architecture/misfiled.md").is_file()


# endregion

# region config and review


def test_config_json_has_every_setting(tmp_path: Path) -> None:
    library = _library(tmp_path)

    output = ConfigOutput.model_validate(_json(["config", "--library", str(library)]))

    assert output.config is not None
    assert output.sync is None
    assert "confidence_threshold" in output.config["classification"]
    assert output.config["classification"]["ambiguity_margin"] == 0.1


def test_config_sync_json_reports_the_sync(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / "Project Phoenix" / "meeting-notes").mkdir()
    (library / "Project Phoenix" / "meeting_notes").mkdir()

    output = ConfigOutput.model_validate(_json(["config", "--library", str(library), "--sync"]))

    assert output.config is None
    assert output.sync is not None
    assert len(output.sync.name_warnings) == 1


def test_review_list_json_works_without_a_terminal(tmp_path: Path) -> None:
    library = _library(tmp_path)

    output = ReviewQueueOutput.model_validate(_json(["review", "--library", str(library), "--list"]))

    assert output.items
    assert all(not entry.confident for entry in output.items)


def test_review_list_without_json_prints_a_line_per_unit(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["review", "--library", str(library), "--list"])

    assert result.exit_code == 0
    assert "SolarConstructionNotes.md" in result.stdout


def test_review_json_without_list_is_refused_as_json(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["review", "--library", str(library), "--json"])

    assert result.exit_code == 1
    assert "--list" in ErrorOutput.model_validate_json(result.stdout).error


# endregion

# region Schemas


@pytest.mark.parametrize("name", sorted(output_schemas()))
def test_output_schema_matches_committed_file(name: str) -> None:
    """If an output model changes, run ``make output-schemas``."""

    committed = json.loads((_SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))

    assert output_schemas()[name] == committed


def test_every_output_carries_a_version() -> None:
    for name, schema in output_schemas().items():
        assert "version" in schema["properties"], name


# endregion
