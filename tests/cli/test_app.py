"""Smoke test that the microfiche CLI exposes all expected commands."""

import re
import shutil
from pathlib import Path

from cli.app import app
from typer.testing import CliRunner

runner = CliRunner()


def test_app_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command_name in ["sort", "review", "propose-categories", "reclassify", "index", "audit", "rollback", "config"]:
        assert command_name in result.stdout


def test_config_command_shows_defaults_for_an_unconfigured_library(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "--library", str(tmp_path)])

    assert result.exit_code == 0
    assert "2" in result.stdout  # library_structure.depth default
    assert "suggest" in result.stdout  # obsidian.tag_mode default


_MOCK_LIBRARY = Path(__file__).resolve().parents[1] / "mock_library"
_PHOENIX_NOTE = "PhoenixArchitectureNotes.md"
_JOB_LINE = re.compile(r"^Job: (\S+)$", re.MULTILINE)


def _library(tmp_path: Path) -> Path:
    library = tmp_path / "library"
    shutil.copytree(_MOCK_LIBRARY, library)
    return library


def _tree(library: Path) -> set[str]:
    """Library-relative path of every file outside microfiche's own state folder."""

    return {
        path.relative_to(library).as_posix()
        for path in library.rglob("*")
        if path.is_file() and ".microfiche" not in path.relative_to(library).parts
    }


def _sort(library: Path) -> str:
    """Run `sort` on ``library`` and return the job id it printed."""

    result = runner.invoke(app, ["sort", "--library", str(library)])
    assert result.exit_code == 0, result.stdout
    match = _JOB_LINE.search(result.stdout)
    assert match is not None, result.stdout
    return match.group(1)


def test_sort_prints_the_job_id_and_how_to_undo_it(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0
    assert "Filed: 1" in result.stdout
    assert "Needs review: 1" in result.stdout
    job_id = _JOB_LINE.search(result.stdout)
    assert job_id is not None
    assert f"microfiche rollback --library <your library> --job-id {job_id.group(1)}" in result.stdout


def test_sort_with_nothing_to_file_prints_no_job(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / "_sorting" / _PHOENIX_NOTE).unlink()

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0
    assert "Filed: 0" in result.stdout
    assert "Job:" not in result.stdout


def test_audit_before_any_sort_says_there_is_no_log(tmp_path: Path) -> None:
    result = runner.invoke(app, ["audit", "--library", str(_library(tmp_path))])

    assert result.exit_code == 0
    assert "No audit log found yet." in result.stdout


def test_audit_shows_the_move_a_sort_made(tmp_path: Path) -> None:
    library = _library(tmp_path)
    job_id = _sort(library)

    result = runner.invoke(app, ["audit", "--library", str(library)])

    assert result.exit_code == 0
    assert f"job={job_id} move _sorting/{_PHOENIX_NOTE} -> Project Phoenix/02 Architecture/{_PHOENIX_NOTE}" in (
        result.stdout
    )


def test_rollback_restores_the_library_and_shows_up_in_the_audit_log(tmp_path: Path) -> None:
    library = _library(tmp_path)
    before = _tree(library)
    job_id = _sort(library)
    assert _tree(library) != before

    result = runner.invoke(app, ["rollback", "--library", str(library), "--job-id", job_id])

    assert result.exit_code == 0
    assert f"Reverted 1 move(s) from job {job_id}." in result.stdout
    assert _tree(library) == before
    audit = runner.invoke(app, ["audit", "--library", str(library)])
    assert f"job={job_id} rollback Project Phoenix/02 Architecture/{_PHOENIX_NOTE} -> _sorting/{_PHOENIX_NOTE}" in (
        audit.stdout
    )


def test_rolling_back_the_same_job_twice_fails_cleanly(tmp_path: Path) -> None:
    library = _library(tmp_path)
    job_id = _sort(library)
    runner.invoke(app, ["rollback", "--library", str(library), "--job-id", job_id])

    result = runner.invoke(app, ["rollback", "--library", str(library), "--job-id", job_id])

    assert result.exit_code == 1
    assert "already rolled back" in result.stdout
    assert "Traceback" not in result.stdout
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_rolling_back_an_unknown_job_fails_cleanly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["rollback", "--library", str(_library(tmp_path)), "--job-id", "nope"])

    assert result.exit_code == 1
    assert "No rollback job found for id 'nope'" in result.stdout


def test_rollback_blocked_by_a_file_in_the_way_explains_how_to_finish_and_can_be_retried(tmp_path: Path) -> None:
    library = _library(tmp_path)
    before = _tree(library)
    job_id = _sort(library)
    blocker = library / "_sorting" / _PHOENIX_NOTE
    blocker.write_text("something new", encoding="utf-8")

    blocked = runner.invoke(app, ["rollback", "--library", str(library), "--job-id", job_id])

    assert blocked.exit_code == 1
    assert "Refusing to overwrite existing path" in blocked.stdout
    assert "re-run the same command" in blocked.stdout

    blocker.unlink()
    retried = runner.invoke(app, ["rollback", "--library", str(library), "--job-id", job_id])

    assert retried.exit_code == 0
    assert _tree(library) == before


_ARCHITECTURE_TEXT = "Project Phoenix architecture decisions."
_MISFILED = "Project Phoenix/03 Research/misfiled.md"
_REFILED = "Project Phoenix/02 Architecture/misfiled.md"


def _library_with_a_misfiled_note(tmp_path: Path) -> Path:
    library = _library(tmp_path)
    (library / _MISFILED).write_text(_ARCHITECTURE_TEXT, encoding="utf-8")
    return library


def test_reclassify_without_apply_previews_the_move_and_changes_nothing(tmp_path: Path) -> None:
    library = _library_with_a_misfiled_note(tmp_path)
    before = _tree(library)

    result = runner.invoke(app, ["reclassify", "--library", str(library)])

    assert result.exit_code == 0
    assert "Action" in result.stdout
    assert "Would move: 1" in result.stdout
    assert "Re-run with --apply" in result.stdout
    assert "Job:" not in result.stdout
    assert _tree(library) == before


def test_reclassify_apply_moves_the_file_and_prints_the_job_id(tmp_path: Path) -> None:
    library = _library_with_a_misfiled_note(tmp_path)

    result = runner.invoke(app, ["reclassify", "--library", str(library), "--apply"])

    assert result.exit_code == 0, result.stdout
    assert "Moved: 1" in result.stdout
    assert _JOB_LINE.search(result.stdout) is not None
    assert (library / _REFILED).exists()
    assert not (library / _MISFILED).exists()


def test_reclassify_apply_is_recorded_in_the_audit_log_and_can_be_rolled_back(tmp_path: Path) -> None:
    library = _library_with_a_misfiled_note(tmp_path)
    before = _tree(library)
    applied = runner.invoke(app, ["reclassify", "--library", str(library), "--apply"])
    match = _JOB_LINE.search(applied.stdout)
    assert match is not None
    job_id = match.group(1)

    audit = runner.invoke(app, ["audit", "--library", str(library)])
    rolled_back = runner.invoke(app, ["rollback", "--library", str(library), "--job-id", job_id])

    assert f"job={job_id} move {_MISFILED} -> {_REFILED}" in audit.stdout
    assert rolled_back.exit_code == 0
    assert _tree(library) == before


def test_reclassify_apply_with_nothing_to_move_prints_no_job(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["reclassify", "--library", str(library), "--apply"])

    assert result.exit_code == 0
    assert "Moved: 0" in result.stdout
    assert "Job:" not in result.stdout


def test_reclassify_apply_reports_a_taken_destination_instead_of_overwriting(tmp_path: Path) -> None:
    library = _library_with_a_misfiled_note(tmp_path)
    (library / _REFILED).write_text("already here", encoding="utf-8")

    result = runner.invoke(app, ["reclassify", "--library", str(library), "--apply"])

    assert result.exit_code == 0
    assert "Skipped, destination taken: 1" in result.stdout
    assert (library / _MISFILED).read_text(encoding="utf-8") == _ARCHITECTURE_TEXT
    assert (library / _REFILED).read_text(encoding="utf-8") == "already here"


def test_reclassify_folder_outside_the_library_fails_cleanly(tmp_path: Path) -> None:
    library = _library(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    result = runner.invoke(app, ["reclassify", "--library", str(library), "--folder", str(outside)])

    assert result.exit_code == 1
    assert "is not inside the library" in result.stdout


# --- library layout: where it lives, what it is called -----------------------------------------


def test_sort_works_for_a_library_kept_under_a_dot_folder(tmp_path: Path) -> None:
    """Regression: a library under a folder like ~/.vaults used to find no groups, so nothing filed."""

    library = tmp_path / ".vaults" / "library"
    shutil.copytree(_MOCK_LIBRARY, library)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "Filed: 1" in result.stdout
    assert (library / "Project Phoenix" / "02 Architecture" / _PHOENIX_NOTE).exists()


def test_reclassify_works_for_a_library_kept_under_an_underscore_folder(tmp_path: Path) -> None:
    library = tmp_path / "_work" / "library"
    shutil.copytree(_MOCK_LIBRARY, library)
    (library / _MISFILED).write_text(_ARCHITECTURE_TEXT, encoding="utf-8")

    result = runner.invoke(app, ["reclassify", "--library", str(library), "--apply"])

    assert result.exit_code == 0, result.stdout
    assert "Moved: 1" in result.stdout
    assert (library / _REFILED).exists()


def test_sort_uses_the_inbox_named_in_the_libraries_config(tmp_path: Path) -> None:
    library = _library(tmp_path)
    config = library / ".microfiche" / "microfiche-config.toml"
    config.write_text(config.read_text(encoding="utf-8").replace('"_sorting"', '"Incoming"', 1), encoding="utf-8")
    (library / "_sorting").rename(library / "Incoming")

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "Filed: 1" in result.stdout
    assert (library / "Project Phoenix" / "02 Architecture" / _PHOENIX_NOTE).exists()
    assert (library / "Incoming" / "SolarConstructionNotes.md").exists()


def test_sort_works_for_a_library_with_no_config_folder_at_all(tmp_path: Path) -> None:
    """Regression: with no config the inbox used to be treated as a group."""

    library = _library(tmp_path)
    shutil.rmtree(library / ".microfiche")

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "Filed: 1" in result.stdout


def test_config_shows_the_library_inbox(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "--library", str(_library(tmp_path))])

    assert result.exit_code == 0
    assert "library_inbox" in result.stdout
    assert "_sorting" in result.stdout


def test_config_shows_the_library_templates(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "--library", str(_library(tmp_path))])

    assert result.exit_code == 0
    assert "library_templates" in result.stdout
    assert "software_project" in result.stdout
    assert "personal_project" in result.stdout


def test_config_still_lists_library_templates_when_the_library_defines_none(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "--library", str(tmp_path)])

    assert result.exit_code == 0
    assert "library_templates" in result.stdout


# --- files that can't be read ------------------------------------------------------------------


def test_sort_files_what_it_can_and_names_the_file_it_could_not_read(tmp_path: Path) -> None:
    """Regression: one corrupt file used to abort the whole sort with a traceback."""

    library = _library(tmp_path)
    (library / "_sorting" / "broken.docx").write_text("this is not a zip file", encoding="utf-8")

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "Filed: 1" in result.stdout
    assert "Needs review: 2" in result.stdout
    assert "broken.docx" in result.stdout
    assert "Could not read 'broken.docx'" in result.stdout
    assert (library / "_sorting" / "broken.docx").exists()
    assert (library / "Project Phoenix" / "02 Architecture" / _PHOENIX_NOTE).exists()


def test_reclassify_names_a_file_it_could_not_read(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / "Project Phoenix" / "03 Research" / "broken.docx").write_text("not a zip", encoding="utf-8")

    result = runner.invoke(app, ["reclassify", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "Could not read 'broken.docx'" in result.stdout
