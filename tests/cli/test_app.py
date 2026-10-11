"""Smoke test that the microfiche CLI exposes all expected commands."""

import re
import shutil
from pathlib import Path

import pytest
from cli.app import app
from core.config import AIConfig
from typer.testing import CliRunner

# region Test helpers


runner = CliRunner()


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


def _bundle_in_inbox(library: Path) -> Path:
    """Put the Phoenix note inside an inbox folder, and return that folder."""

    bundle = library / "_sorting" / "bundle"
    bundle.mkdir()
    (library / "_sorting" / _PHOENIX_NOTE).rename(bundle / _PHOENIX_NOTE)
    return bundle


def _set_keep_folders(library: Path, value: bool) -> None:
    config = library / ".microfiche" / "microfiche-config.toml"
    config.write_text(
        config.read_text(encoding="utf-8") + f"\n[sorting]\nkeep_folders = {str(value).lower()}\n", encoding="utf-8"
    )


def _sort(library: Path) -> str:
    """Run `sort` on ``library`` and return the job id it printed."""

    result = runner.invoke(app, ["sort", "--library", str(library)])
    assert result.exit_code == 0, result.stdout
    match = _JOB_LINE.search(result.stdout)
    assert match is not None, result.stdout
    return match.group(1)


# endregion


# region Help and config


def test_app_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command_name in ["sort", "review", "propose-categories", "reclassify", "index", "audit", "rollback", "config"]:
        assert command_name in result.stdout


def test_config_shows_defaults_for_unconfigured_library(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "--library", str(tmp_path)])

    assert result.exit_code == 0
    assert "2" in result.stdout  # library_structure.depth default
    assert "suggest" in result.stdout  # obsidian.tag_mode default


# endregion


# region Sort, audit and rollback


def test_sort_prints_job_id_and_undo_hint(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0
    assert "Filed: 1" in result.stdout
    assert "Needs review: 1" in result.stdout
    job_id = _JOB_LINE.search(result.stdout)
    assert job_id is not None
    assert f"microfiche rollback --library <your library> --job-id {job_id.group(1)}" in result.stdout


def test_sort_nothing_to_file_prints_no_job(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / "_sorting" / _PHOENIX_NOTE).unlink()

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0
    assert "Filed: 0" in result.stdout
    assert "Job:" not in result.stdout


def test_audit_before_sort_says_no_log(tmp_path: Path) -> None:
    result = runner.invoke(app, ["audit", "--library", str(_library(tmp_path))])

    assert result.exit_code == 0
    assert "No audit log found yet." in result.stdout


def test_audit_shows_sort_move(tmp_path: Path) -> None:
    library = _library(tmp_path)
    job_id = _sort(library)

    result = runner.invoke(app, ["audit", "--library", str(library)])

    assert result.exit_code == 0
    assert f"job={job_id} move _sorting/{_PHOENIX_NOTE} -> Project Phoenix/02 Architecture/{_PHOENIX_NOTE}" in (
        result.stdout
    )


def test_rollback_restores_library_and_appears_in_audit(tmp_path: Path) -> None:
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


def test_rollback_same_job_twice_fails_cleanly(tmp_path: Path) -> None:
    library = _library(tmp_path)
    job_id = _sort(library)
    runner.invoke(app, ["rollback", "--library", str(library), "--job-id", job_id])

    result = runner.invoke(app, ["rollback", "--library", str(library), "--job-id", job_id])

    assert result.exit_code == 1
    assert "already rolled back" in result.stdout
    assert "Traceback" not in result.stdout
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_rollback_unknown_job_fails_cleanly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["rollback", "--library", str(_library(tmp_path)), "--job-id", "nope"])

    assert result.exit_code == 1
    assert "No rollback job found for id 'nope'" in result.stdout


def test_rollback_blocked_by_file_explains_and_retries(tmp_path: Path) -> None:
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


# endregion


# region Keeping inbox folders whole


def test_sort_inbox_folder_filed_whole_by_default(tmp_path: Path) -> None:
    library = _library(tmp_path)
    bundle = _bundle_in_inbox(library)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert (library / "Project Phoenix" / "02 Architecture" / "bundle" / _PHOENIX_NOTE).exists()
    assert not bundle.exists()


def test_sort_keep_folders_off_in_config_leaves_inbox_folder(tmp_path: Path) -> None:
    library = _library(tmp_path)
    bundle = _bundle_in_inbox(library)
    _set_keep_folders(library, False)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert (bundle / _PHOENIX_NOTE).exists()


def test_sort_keep_folders_flag_overrides_config_off(tmp_path: Path) -> None:
    library = _library(tmp_path)
    bundle = _bundle_in_inbox(library)
    _set_keep_folders(library, False)

    result = runner.invoke(app, ["sort", "--library", str(library), "--keep-folders"])

    assert result.exit_code == 0, result.stdout
    assert not bundle.exists()


def test_sort_keep_folders_off_flag_overrides_default(tmp_path: Path) -> None:
    library = _library(tmp_path)
    bundle = _bundle_in_inbox(library)

    result = runner.invoke(app, ["sort", "--library", str(library), "--keep-folders-off"])

    assert result.exit_code == 0, result.stdout
    assert (bundle / _PHOENIX_NOTE).exists()


def test_sort_both_keep_folders_flags_fail_without_sorting(tmp_path: Path) -> None:
    library = _library(tmp_path)
    before = _tree(library)

    result = runner.invoke(app, ["sort", "--library", str(library), "--keep-folders", "--keep-folders-off"])

    assert result.exit_code == 1
    assert "--keep-folders" in result.stdout
    assert "--keep-folders-off" in result.stdout
    assert _tree(library) == before


def test_propose_categories_uses_keep_folders_setting(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _bundle_in_inbox(library)
    _set_keep_folders(library, False)

    result = runner.invoke(app, ["propose-categories", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "PhoenixArchitectureNotes" not in result.stdout  # the folder's document is not read


# endregion


# region AI fallback


class _NoAnswerProvider:
    """An AI provider that always says no group fits."""

    def complete(self, prompt: str) -> str:
        return "NONE"


@pytest.fixture
def built_with(monkeypatch: pytest.MonkeyPatch) -> list[AIConfig]:
    """Replace the provider factory with a fake, and record the settings it was asked to build from."""

    seen: list[AIConfig] = []

    def fake_build_provider(config: AIConfig) -> _NoAnswerProvider:
        seen.append(config)
        return _NoAnswerProvider()

    monkeypatch.setattr("cli.commands.build_provider", fake_build_provider)
    return seen


def _set_ai(library: Path, settings: str) -> None:
    config = library / ".microfiche" / "microfiche-config.toml"
    config.write_text(config.read_text(encoding="utf-8") + "\n[ai]\n" + settings, encoding="utf-8")


def test_sort_use_ai_builds_the_configured_provider(tmp_path: Path, built_with: list[AIConfig]) -> None:
    library = _library(tmp_path)
    _set_ai(library, 'model = "mistral"\n')

    result = runner.invoke(app, ["sort", "--library", str(library), "--use-ai"])

    assert result.exit_code == 0, result.stdout
    (config,) = built_with
    assert (config.provider, config.model) == ("ollama", "mistral")


def test_sort_without_use_ai_builds_no_provider(tmp_path: Path, built_with: list[AIConfig]) -> None:
    result = runner.invoke(app, ["sort", "--library", str(_library(tmp_path))])

    assert result.exit_code == 0, result.stdout
    assert built_with == []


def test_sort_use_ai_default_settings_print_no_warning(tmp_path: Path, built_with: list[AIConfig]) -> None:
    result = runner.invoke(app, ["sort", "--library", str(_library(tmp_path)), "--use-ai"])

    assert "OpenAI" not in result.stdout
    assert "no limit" not in result.stdout


def test_sort_use_ai_openai_says_text_is_sent_to_openai(tmp_path: Path, built_with: list[AIConfig]) -> None:
    library = _library(tmp_path)
    _set_ai(library, 'provider = "openai"\n')

    result = runner.invoke(app, ["sort", "--library", str(library), "--use-ai"])

    assert result.exit_code == 0, result.stdout
    assert "sent to OpenAI" in result.stdout


def test_sort_openai_configured_but_no_use_ai_says_nothing(tmp_path: Path, built_with: list[AIConfig]) -> None:
    library = _library(tmp_path)
    _set_ai(library, 'provider = "openai"\n')

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert "OpenAI" not in result.stdout  # nothing is sent without --use-ai


def test_sort_use_ai_unlimited_warns_once_not_per_document(tmp_path: Path, built_with: list[AIConfig]) -> None:
    library = _library(tmp_path)
    _set_ai(library, "max_document_chars = 0\n")
    (library / "_sorting" / "Another.md").write_text("Nothing recognisable here.", encoding="utf-8")

    result = runner.invoke(app, ["sort", "--library", str(library), "--use-ai"])

    assert result.exit_code == 0, result.stdout
    assert result.stdout.count("no limit") == 1
    assert "context window" in result.stdout


def test_sort_use_ai_unlimited_with_openai_mentions_billing(tmp_path: Path, built_with: list[AIConfig]) -> None:
    library = _library(tmp_path)
    _set_ai(library, 'provider = "openai"\nmax_document_chars = 0\n')

    result = runner.invoke(app, ["sort", "--library", str(library), "--use-ai"])

    assert "bills" in result.stdout


def test_sort_use_ai_openai_without_key_fails_cleanly_and_sorts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _library(tmp_path)
    _set_ai(library, 'provider = "openai"\n')
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    before = _tree(library)

    result = runner.invoke(app, ["sort", "--library", str(library), "--use-ai"])

    assert result.exit_code == 1
    assert "OPENAI_API_KEY" in result.stdout
    assert _tree(library) == before


# endregion


# region Reclassify


_ARCHITECTURE_TEXT = "Project Phoenix architecture decisions."
_MISFILED = "Project Phoenix/03 Research/misfiled.md"
_REFILED = "Project Phoenix/02 Architecture/misfiled.md"


def _library_with_a_misfiled_note(tmp_path: Path) -> Path:
    library = _library(tmp_path)
    (library / _MISFILED).write_text(_ARCHITECTURE_TEXT, encoding="utf-8")
    return library


def test_reclassify_without_apply_previews_only(tmp_path: Path) -> None:
    library = _library_with_a_misfiled_note(tmp_path)
    before = _tree(library)

    result = runner.invoke(app, ["reclassify", "--library", str(library)])

    assert result.exit_code == 0
    assert "Action" in result.stdout
    assert "Would move: 1" in result.stdout
    assert "Re-run with --apply" in result.stdout
    assert "Job:" not in result.stdout
    assert _tree(library) == before


def test_reclassify_apply_moves_file_and_prints_job_id(tmp_path: Path) -> None:
    library = _library_with_a_misfiled_note(tmp_path)

    result = runner.invoke(app, ["reclassify", "--library", str(library), "--apply"])

    assert result.exit_code == 0, result.stdout
    assert "Moved: 1" in result.stdout
    assert _JOB_LINE.search(result.stdout) is not None
    assert (library / _REFILED).exists()
    assert not (library / _MISFILED).exists()


def test_reclassify_apply_audited_and_rollbackable(tmp_path: Path) -> None:
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


def test_reclassify_apply_nothing_to_move_prints_no_job(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["reclassify", "--library", str(library), "--apply"])

    assert result.exit_code == 0
    assert "Moved: 0" in result.stdout
    assert "Job:" not in result.stdout


def test_reclassify_apply_taken_destination_not_overwritten(tmp_path: Path) -> None:
    library = _library_with_a_misfiled_note(tmp_path)
    (library / _REFILED).write_text("already here", encoding="utf-8")

    result = runner.invoke(app, ["reclassify", "--library", str(library), "--apply"])

    assert result.exit_code == 0
    assert "Skipped, destination taken: 1" in result.stdout
    assert (library / _MISFILED).read_text(encoding="utf-8") == _ARCHITECTURE_TEXT
    assert (library / _REFILED).read_text(encoding="utf-8") == "already here"


def test_reclassify_folder_outside_library_fails_cleanly(tmp_path: Path) -> None:
    library = _library(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    result = runner.invoke(app, ["reclassify", "--library", str(library), "--folder", str(outside)])

    assert result.exit_code == 1
    assert "is not inside the library" in result.stdout


# endregion


# region Library layout: where it lives, what it is called


def test_sort_library_under_dot_folder(tmp_path: Path) -> None:
    """Regression: a library under a folder like ~/.vaults used to find no groups, so nothing filed."""

    library = tmp_path / ".vaults" / "library"
    shutil.copytree(_MOCK_LIBRARY, library)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "Filed: 1" in result.stdout
    assert (library / "Project Phoenix" / "02 Architecture" / _PHOENIX_NOTE).exists()


def test_reclassify_library_under_underscore_folder(tmp_path: Path) -> None:
    library = tmp_path / "_work" / "library"
    shutil.copytree(_MOCK_LIBRARY, library)
    (library / _MISFILED).write_text(_ARCHITECTURE_TEXT, encoding="utf-8")

    result = runner.invoke(app, ["reclassify", "--library", str(library), "--apply"])

    assert result.exit_code == 0, result.stdout
    assert "Moved: 1" in result.stdout
    assert (library / _REFILED).exists()


def test_sort_uses_inbox_named_in_config(tmp_path: Path) -> None:
    library = _library(tmp_path)
    config = library / ".microfiche" / "microfiche-config.toml"
    config.write_text(config.read_text(encoding="utf-8").replace('"_sorting"', '"Incoming"', 1), encoding="utf-8")
    (library / "_sorting").rename(library / "Incoming")

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "Filed: 1" in result.stdout
    assert (library / "Project Phoenix" / "02 Architecture" / _PHOENIX_NOTE).exists()
    assert (library / "Incoming" / "SolarConstructionNotes.md").exists()


def test_sort_library_without_config_folder(tmp_path: Path) -> None:
    """Regression: with no config the inbox used to be treated as a group."""

    library = _library(tmp_path)
    shutil.rmtree(library / ".microfiche")

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "Filed: 1" in result.stdout


def test_config_shows_library_inbox(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "--library", str(_library(tmp_path))])

    assert result.exit_code == 0
    assert "library_inbox" in result.stdout
    assert "_sorting" in result.stdout


def test_config_shows_depth_and_no_removed_settings(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "--library", str(_library(tmp_path))])

    assert result.exit_code == 0
    assert "depth" in result.stdout
    for removed in ("library_templates", "file_target_level", "category_hints", "filing_rules"):
        assert removed not in result.stdout


def test_sort_unsupported_depth_stops_with_clear_message(tmp_path: Path) -> None:
    library = _library(tmp_path)
    config = library / ".microfiche" / "microfiche-config.toml"
    config.write_text(config.read_text(encoding="utf-8").replace("depth = 2", "depth = 3"), encoding="utf-8")

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 1
    assert "depth 3 is not supported" in result.stdout


# endregion


# region Files that can't be read


def test_sort_files_readable_and_names_unreadable_file(tmp_path: Path) -> None:
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


def test_reclassify_names_unreadable_file(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / "Project Phoenix" / "03 Research" / "broken.docx").write_text("not a zip", encoding="utf-8")

    result = runner.invoke(app, ["reclassify", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "Could not read 'broken.docx'" in result.stdout


# endregion


# region A config that can't be used


def _break_config(library: Path) -> None:
    (library / ".microfiche" / "microfiche-config.toml").write_text(
        '[classification]\nconfidence_threshold = "high"\n', encoding="utf-8"
    )


@pytest.mark.parametrize("command", ["sort", "reclassify", "propose-categories", "config"])
def test_commands_invalid_config_stops_with_clear_message(tmp_path: Path, command: str) -> None:
    library = _library(tmp_path)
    _break_config(library)

    result = runner.invoke(app, [command, "--library", str(library)])

    assert result.exit_code == 1
    assert "classification.confidence_threshold" in result.stdout
    assert isinstance(result.exception, SystemExit)  # a clean exit, not an uncaught ConfigError


def _break_library_file(library: Path) -> None:
    (library / ".microfiche" / "microfiche-library.json").write_text(
        '{"groups": [{"name": "A", "hint": []}]}', encoding="utf-8"
    )


@pytest.mark.parametrize("command", ["sort", "reclassify"])
def test_commands_using_hints_invalid_library_file_stops_with_clear_message(tmp_path: Path, command: str) -> None:
    library = _library(tmp_path)
    _break_library_file(library)
    before = _tree(library)

    result = runner.invoke(app, [command, "--library", str(library)])

    assert result.exit_code == 1
    assert "groups[0].hint: unknown key" in result.stdout
    assert isinstance(result.exception, SystemExit)  # a clean exit, not an uncaught ConfigError
    assert _tree(library) == before


@pytest.mark.parametrize("command", ["propose-categories", "config", "audit"])
def test_commands_not_using_hints_work_with_invalid_library_file(tmp_path: Path, command: str) -> None:
    library = _library(tmp_path)
    _break_library_file(library)

    result = runner.invoke(app, [command, "--library", str(library)])

    assert result.exit_code == 0, result.stdout


def test_sort_files_by_hints_from_the_library_file(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert (library / "Project Phoenix" / "02 Architecture" / _PHOENIX_NOTE).exists()


def test_rollback_and_audit_work_with_invalid_config(tmp_path: Path) -> None:
    library = _library(tmp_path)
    job_id = _sort(library)
    _break_config(library)

    audit = runner.invoke(app, ["audit", "--library", str(library)])
    rollback = runner.invoke(app, ["rollback", "--library", str(library), "--job-id", job_id])

    assert audit.exit_code == 0
    assert rollback.exit_code == 0
    assert "Reverted 1 move(s)" in rollback.stdout


# endregion
