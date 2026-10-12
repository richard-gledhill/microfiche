"""Smoke test that the microfiche CLI exposes all expected commands."""

import json
import logging
import os
import re
import shutil
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

import pytest
from cli.app import app
from conftest import LinkMaker
from core.config import AIConfig
from core.library.library import Library
from core.runlock import run_lock
from typer.testing import CliRunner

# region Test helpers


runner = CliRunner()


_MOCK_LIBRARY = Path(__file__).resolve().parents[1] / "mock_library"
_PHOENIX_NOTE = "PhoenixArchitectureNotes.md"
_PACK = "phoenix-weekly-pack"  # an inbox folder in the mock library, for the folder tests
_JOB_LINE = re.compile(r"^Job: (\S+)$", re.MULTILINE)


def _library(tmp_path: Path, *, with_pack: bool = False) -> Path:
    """A copy of the mock library; most tests are about its two loose notes, so ``_PACK`` is left out."""

    library = tmp_path / "library"
    shutil.copytree(_MOCK_LIBRARY, library)
    if not with_pack:
        shutil.rmtree(library / "_sorting" / _PACK)
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
    for command_name in ["sort", "review", "propose-categories", "reclassify", "audit", "rollback", "config"]:
        assert command_name in result.stdout


def test_app_index_command_removed() -> None:
    # `index` regenerated Obsidian folder notes; it left the MVP with the integration (docs/development/feature-backlog.md).
    result = runner.invoke(app, ["index", "--help"])

    assert result.exit_code == 2
    assert "No such command" in result.output


def test_config_shows_defaults_for_unconfigured_library(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "--library", str(tmp_path)])

    assert result.exit_code == 0
    assert "2" in result.stdout  # library_structure.depth default
    assert "microfiche.log" in result.stdout  # logging.file default


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


def test_sort_keep_folders_off_in_config_files_documents_one_by_one(tmp_path: Path) -> None:
    library = _library(tmp_path)
    bundle = _bundle_in_inbox(library)
    _set_keep_folders(library, False)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert (library / "Project Phoenix" / "02 Architecture" / _PHOENIX_NOTE).exists()
    assert not bundle.exists()  # emptied, so removed
    assert "Removed the emptied inbox folder" in result.stdout


def test_sort_keep_folders_flag_overrides_config_off(tmp_path: Path) -> None:
    library = _library(tmp_path)
    bundle = _bundle_in_inbox(library)
    _set_keep_folders(library, False)

    result = runner.invoke(app, ["sort", "--library", str(library), "--keep-folders"])

    assert result.exit_code == 0, result.stdout
    assert not bundle.exists()


def test_rollback_after_emptied_folder_removal_recreates_folder(tmp_path: Path) -> None:
    library = _library(tmp_path)
    bundle = _bundle_in_inbox(library)
    before = _tree(library)
    result = runner.invoke(app, ["sort", "--library", str(library), "--keep-folders-off"])
    assert result.exit_code == 0, result.stdout
    assert not bundle.exists()
    match = _JOB_LINE.search(result.stdout)
    assert match is not None, result.stdout
    job_id = match.group(1)

    result = runner.invoke(app, ["rollback", "--library", str(library), "--job-id", job_id])

    assert result.exit_code == 0, result.stdout
    assert "Reverted 1 move(s) and recreated 1 emptied folder(s)" in " ".join(result.stdout.split())
    assert bundle.is_dir()
    assert _tree(library) == before


def test_sort_keep_folders_off_flag_overrides_default(tmp_path: Path) -> None:
    library = _library(tmp_path)
    bundle = _bundle_in_inbox(library)
    (bundle / "photo.png").write_bytes(b"not a document")

    result = runner.invoke(app, ["sort", "--library", str(library), "--keep-folders-off"])

    assert result.exit_code == 0, result.stdout
    assert (library / "Project Phoenix" / "02 Architecture" / _PHOENIX_NOTE).exists()
    assert (bundle / "photo.png").exists()  # not a document, so the folder stays
    assert "bundle stays in the inbox: it still holds photo.png (not sorted)" in " ".join(result.stdout.split())


def test_sort_both_keep_folders_flags_fail_without_sorting(tmp_path: Path) -> None:
    library = _library(tmp_path)
    before = _tree(library)

    result = runner.invoke(app, ["sort", "--library", str(library), "--keep-folders", "--keep-folders-off"])

    assert result.exit_code == 1
    assert "--keep-folders" in result.stdout
    assert "--keep-folders-off" in result.stdout
    assert _tree(library) == before


@pytest.mark.parametrize("keep_folders", [True, False])
def test_propose_categories_reads_folder_documents_either_way(tmp_path: Path, keep_folders: bool) -> None:
    library = _library(tmp_path)
    _bundle_in_inbox(library)
    _set_keep_folders(library, keep_folders)

    result = runner.invoke(app, ["propose-categories", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "PhoenixArchitectureNotes" in result.stdout  # the folder's document is read whether or not it is kept whole


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
    assert "Filed: 2" in result.stdout  # the Phoenix note and the mock library's inbox folder
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


# region Duplicates


def test_sort_lists_duplicates_with_reason_and_leaves_them_in_inbox(tmp_path: Path) -> None:
    library = _library(tmp_path)
    filed_copy = library / "Project Phoenix" / "02 Architecture" / _PHOENIX_NOTE
    shutil.copyfile(library / "_sorting" / _PHOENIX_NOTE, filed_copy)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    output = " ".join(result.stdout.split())
    assert "Duplicates (left in the inbox): 1" in output
    assert f"{_PHOENIX_NOTE} — identical to Project Phoenix/02 Architecture/{_PHOENIX_NOTE}, already filed" in output
    assert (library / "_sorting" / _PHOENIX_NOTE).exists()
    assert "Job:" not in result.stdout  # nothing was filed, so there is nothing to undo


def test_sort_without_duplicates_prints_zero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["sort", "--library", str(_library(tmp_path))])

    assert result.exit_code == 0, result.stdout
    assert "Duplicates (left in the inbox): 0" in result.stdout


# endregion


# region Input hardening


def test_sort_reports_skipped_link(tmp_path: Path, make_junction: LinkMaker) -> None:
    library = _library(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    make_junction(library / "_sorting" / "linked-folder", elsewhere)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "Skipped linked-folder: links and junctions are never followed" in " ".join(result.stdout.split())


def test_sort_oversize_file_listed_with_reason(tmp_path: Path) -> None:
    library = _library(tmp_path)
    config = library / ".microfiche" / "microfiche-config.toml"
    config.write_text(config.read_text(encoding="utf-8") + "\n[parsing]\nmax_file_mb = 1\n", encoding="utf-8")
    (library / "_sorting" / "huge.md").write_bytes(b"x" * 2 * 1024 * 1024)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "huge.md" in result.stdout
    assert "over the 1 MB limit" in " ".join(result.stdout.split())
    assert (library / "_sorting" / "huge.md").exists()


# endregion


# region Failures that belong to one unit


class _DownProvider:
    """An AI provider that cannot be reached."""

    _error = ConnectionError("connection refused")

    def complete(self, prompt: str) -> str:
        raise self._error


def test_sort_use_ai_provider_down_warns_once_and_still_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _library(tmp_path)
    (library / "_sorting" / "unknown-one.md").write_text("Nothing recognisable in here.", encoding="utf-8")
    (library / "_sorting" / "unknown-two.md").write_text("Nor in here.", encoding="utf-8")
    monkeypatch.setattr("cli.commands.build_provider", lambda config: _DownProvider())

    result = runner.invoke(app, ["sort", "--library", str(library), "--use-ai"])

    assert result.exit_code == 0, result.stdout
    # The warning is a log record now, shown once on stderr; the report no longer prints a line of its own.
    assert "AI fallback unavailable" not in result.stdout
    warning = " ".join(result.stderr.split())
    assert warning.count("AI fallback unavailable") == 1
    assert "ConnectionError: connection refused" in warning
    assert "uses the rules only" in warning
    assert (library / "Project Phoenix" / "02 Architecture" / _PHOENIX_NOTE).exists()


def test_sort_open_file_listed_for_review_with_reason(tmp_path: Path, hold_open: Callable[[Path], None]) -> None:
    library = _library(tmp_path)
    hold_open(library / "_sorting" / _PHOENIX_NOTE)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout  # a locked file is not a failure of the run
    assert "it is open in another program; close it and sort again" in " ".join(result.stdout.split())
    assert (library / "_sorting" / _PHOENIX_NOTE).exists()


def test_reclassify_apply_move_that_fails_is_listed_and_left_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _library_with_a_misfiled_note(tmp_path)

    def refuse(source: Path, destination: Path) -> Path:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("core.filer.safe_move", refuse)

    result = runner.invoke(app, ["reclassify", "--library", str(library), "--apply"])

    assert result.exit_code == 0, result.stdout
    output = " ".join(result.stdout.split())
    assert "Moved: 0" in output
    assert "could not be moved: permission denied" in output
    assert (library / _MISFILED).exists()
    assert "Job:" not in result.stdout  # nothing moved, so nothing to undo


# endregion


# region Dry run


def test_sort_dry_run_previews_without_moving_or_recording(tmp_path: Path) -> None:
    library = _library(tmp_path)
    before = _tree(library)

    result = runner.invoke(app, ["sort", "--library", str(library), "--dry-run"])

    assert result.exit_code == 0, result.stdout
    output = " ".join(result.stdout.split())
    assert "Preview: nothing was moved, and nothing was recorded." in output
    assert "Would file: 1" in output
    assert f"{_PHOENIX_NOTE} -> Project Phoenix/02 Architecture" in output
    assert "Run again without --dry-run to file these." in output
    assert "Filed:" not in output
    assert "Job:" not in output  # there is nothing to undo
    assert _tree(library) == before
    state = library / ".microfiche"
    assert not (state / "rollback").exists()
    assert not (state / "ledger.jsonl").exists()
    assert not (state / "audit.log").exists()


def test_sort_dry_run_then_real_run_files_what_the_preview_listed(tmp_path: Path) -> None:
    library = _library(tmp_path)
    runner.invoke(app, ["sort", "--library", str(library), "--dry-run"])

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "Filed: 1" in result.stdout
    assert (library / "Project Phoenix" / "02 Architecture" / _PHOENIX_NOTE).exists()


def test_sort_dry_run_nothing_to_file_gives_no_run_again_hint(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / "_sorting" / _PHOENIX_NOTE).unlink()

    result = runner.invoke(app, ["sort", "--library", str(library), "--dry-run"])

    assert result.exit_code == 0, result.stdout
    assert "Would file: 0" in result.stdout
    assert "Run again" not in result.stdout


def test_sort_dry_run_keep_folders_off_says_folder_would_be_removed(tmp_path: Path) -> None:
    library = _library(tmp_path)
    bundle = _bundle_in_inbox(library)

    result = runner.invoke(app, ["sort", "--library", str(library), "--keep-folders-off", "--dry-run"])

    assert result.exit_code == 0, result.stdout
    assert "Would remove the emptied inbox folder bundle" in " ".join(result.stdout.split())
    assert (bundle / _PHOENIX_NOTE).exists()  # untouched


# endregion


# region Library file sync


_LIBRARY_FILE = ".microfiche/microfiche-library.json"


def _without_library_file(library: Path) -> Path:
    path = library / _LIBRARY_FILE
    path.unlink()
    return path


def test_sort_no_library_file_creates_it_and_says_so(tmp_path: Path) -> None:
    library = _library(tmp_path)
    path = _without_library_file(library)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert path.is_file()
    assert "Created microfiche-library.json listing 4 folder(s)" in " ".join(result.stdout.split())


def test_sort_dry_run_writes_no_library_file(tmp_path: Path) -> None:
    library = _library(tmp_path)
    path = _without_library_file(library)

    result = runner.invoke(app, ["sort", "--library", str(library), "--dry-run"])

    assert result.exit_code == 0, result.stdout
    assert not path.exists()
    assert "Created" not in result.stdout


def test_sort_new_folder_reported_once(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _without_library_file(library)
    runner.invoke(app, ["sort", "--library", str(library)])
    (library / "Project Phoenix" / "04 Retrospectives").mkdir()

    first = runner.invoke(app, ["sort", "--library", str(library)])
    second = runner.invoke(app, ["sort", "--library", str(library)])

    assert "Added Project Phoenix/04 Retrospectives to microfiche-library.json" in " ".join(first.stdout.split())
    assert "Retrospectives" not in second.stdout


def test_sort_entry_with_no_folder_reported_every_run(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / _LIBRARY_FILE).write_text(
        json.dumps({"groups": [{"name": "Old Project"}, {"name": "*"}]}), encoding="utf-8"
    )

    first = runner.invoke(app, ["sort", "--library", str(library)])
    second = runner.invoke(app, ["sort", "--library", str(library)])

    for result in (first, second):
        assert "Old Project is in microfiche-library.json but has no folder" in " ".join(result.stdout.split())


def test_config_sync_adds_folders_and_lists_them(tmp_path: Path) -> None:
    library = _library(tmp_path)
    path = _without_library_file(library)

    result = runner.invoke(app, ["config", "--library", str(library), "--sync"])

    assert result.exit_code == 0, result.stdout
    assert "Created microfiche-library.json listing 4 folder(s)" in " ".join(result.stdout.split())
    assert path.is_file()
    assert "Library configuration" not in result.stdout  # --sync shows the sync, not the settings


def test_config_sync_nothing_to_do_says_so(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["config", "--library", str(library), "--sync"])

    assert result.exit_code == 0, result.stdout
    assert "The library file already lists every folder." in result.stdout


def test_config_sync_reports_entry_with_no_folder_and_keeps_it(tmp_path: Path) -> None:
    library = _library(tmp_path)
    written = json.dumps({"groups": [{"name": "Old Project", "hints": ["old"]}, {"name": "*"}]})
    (library / _LIBRARY_FILE).write_text(written, encoding="utf-8")

    result = runner.invoke(app, ["config", "--library", str(library), "--sync"])

    assert result.exit_code == 0, result.stdout
    assert "Old Project is in microfiche-library.json but has no folder" in " ".join(result.stdout.split())
    assert (library / _LIBRARY_FILE).read_text(encoding="utf-8") == written


def test_config_without_sync_writes_nothing(tmp_path: Path) -> None:
    library = _library(tmp_path)
    path = _without_library_file(library)

    result = runner.invoke(app, ["config", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert not path.exists()
    assert not (library / ".microfiche" / "microfiche.log").exists()


def test_config_sync_invalid_library_file_exits_1_untouched(tmp_path: Path) -> None:
    library = _library(tmp_path)
    path = library / _LIBRARY_FILE
    path.write_text('{"groups": [{"name": "A", "bogus": 1}]}', encoding="utf-8")

    result = runner.invoke(app, ["config", "--library", str(library), "--sync"])

    assert result.exit_code == 1
    assert "Library file error" in " ".join(result.stdout.split())
    assert path.read_text(encoding="utf-8") == '{"groups": [{"name": "A", "bogus": 1}]}'


@pytest.mark.usefixtures("library_file_locked")
def test_config_sync_write_failure_exits_1(tmp_path: Path) -> None:
    library = _library(tmp_path)
    _without_library_file(library)

    result = runner.invoke(app, ["config", "--library", str(library), "--sync"])

    assert result.exit_code == 1
    assert "Could not update the library file" in " ".join(result.stdout.split())


def test_config_sync_refused_while_lock_held(tmp_path: Path) -> None:
    library = _library(tmp_path)
    path = _without_library_file(library)

    with run_lock(Library(library), "sort"):
        result = runner.invoke(app, ["config", "--library", str(library), "--sync"])

    assert result.exit_code == 1
    assert "Another microfiche run is already in progress" in " ".join(result.stdout.split())
    assert not path.exists()


# endregion


# region Flat library (depth 1)


_MOCK_FLAT_LIBRARY = Path(__file__).resolve().parents[1] / "mock_flat_library"


def _flat_library(tmp_path: Path) -> Path:
    """A copy of the flat mock library, without its inbox folder."""

    library = tmp_path / "flat"
    shutil.copytree(_MOCK_FLAT_LIBRARY, library)
    shutil.rmtree(library / "_sorting" / "mixed-pack")
    return library


def test_sort_flat_library_files_into_group_folders_and_says_so(tmp_path: Path) -> None:
    library = _flat_library(tmp_path)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    output = " ".join(result.stdout.split())
    assert "Filed: 4" in output
    assert "PhoenixDesignNotes.md -> Project Phoenix (confidence 1.00, via rules_engine)" in output
    assert "electricity-march.md -> Household (confidence 0.75, via rules_engine)" in output
    assert "None" not in output
    assert (library / "Project Phoenix" / "PhoenixDesignNotes.md").is_file()
    assert "HolidayIdeas.md" in output  # left for review, with a reason that names no category


def test_sort_dry_run_flat_library_previews_the_group(tmp_path: Path) -> None:
    library = _flat_library(tmp_path)
    before = _tree(library)

    result = runner.invoke(app, ["sort", "--library", str(library), "--dry-run"])

    assert result.exit_code == 0, result.stdout
    assert "AtlasBudget.md -> Project Atlas" in " ".join(result.stdout.split())
    assert _tree(library) == before


def test_sort_flat_library_rollback_restores_it(tmp_path: Path) -> None:
    library = _flat_library(tmp_path)
    before = _tree(library)
    job_id = _sort(library)

    result = runner.invoke(app, ["rollback", "--library", str(library), "--job-id", job_id])

    assert result.exit_code == 0, result.stdout
    assert _tree(library) == before


def test_reclassify_flat_library_dry_run_lists_the_group_without_a_category(tmp_path: Path) -> None:
    library = _flat_library(tmp_path)
    shutil.move(library / "Project Atlas" / "scope.md", library / "Household" / "scope.md")

    result = runner.invoke(app, ["reclassify", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    output = " ".join(result.stdout.split())
    assert "Would move: 1" in output
    assert "Project Atlas" in output
    assert "None" not in output
    assert "Proposed group" in output
    assert "Proposed category" not in output  # a flat library has no categories


def test_propose_categories_flat_library_says_there_are_none(tmp_path: Path) -> None:
    library = _flat_library(tmp_path)

    result = runner.invoke(app, ["propose-categories", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "no categories to propose" in " ".join(result.stdout.split())


def test_config_sync_flat_library_lists_group_folders_only(tmp_path: Path) -> None:
    library = _flat_library(tmp_path)
    (library / _LIBRARY_FILE).write_text(json.dumps({"groups": []}), encoding="utf-8")

    result = runner.invoke(app, ["config", "--library", str(library), "--sync"])

    assert result.exit_code == 0, result.stdout
    output = " ".join(result.stdout.split())
    assert "Added Household to microfiche-library.json" in output
    assert "Added Project Atlas to microfiche-library.json" in output
    assert "/" not in output.split("microfiche-library.json", 1)[0]  # no category entries (Group/Category)


def test_sort_flat_library_library_file_with_categories_is_refused(tmp_path: Path) -> None:
    library = _flat_library(tmp_path)
    (library / _LIBRARY_FILE).write_text(
        json.dumps({"groups": [{"name": "Household", "children": [{"name": "Bills"}]}]}), encoding="utf-8"
    )

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 1
    output = " ".join(result.stdout.split())
    assert "describes 2 levels of folders, but the library's depth is 1" in output
    assert "remove the entries below the top level, or raise the depth" in output


# endregion


# region Run lock


_LOCK = ".microfiche/lock"
_IN_PROGRESS = "Another microfiche run is already in progress"


def _held(library: Path) -> AbstractContextManager[None]:
    """Hold the run lock, as another run in progress would."""

    return run_lock(Library(library), "sort")


def test_sort_refused_while_another_run_holds_the_lock(tmp_path: Path) -> None:
    library = _library(tmp_path)
    before = _tree(library)

    with _held(library):
        result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 1
    assert _IN_PROGRESS in " ".join(result.stdout.split())
    assert f"process {os.getpid()}" in result.stdout
    assert _tree(library) == before  # nothing was moved
    assert not (library / ".microfiche" / "rollback").exists()


@pytest.mark.parametrize("command", ["rollback", "reclassify"])
def test_other_changing_commands_refused_while_lock_held(tmp_path: Path, command: str) -> None:
    library = _library(tmp_path)
    arguments = ["--job-id", "20260101-000000-abcdef"] if command == "rollback" else ["--apply"]

    with _held(library):
        result = runner.invoke(app, [command, "--library", str(library), *arguments])

    assert result.exit_code == 1
    assert _IN_PROGRESS in " ".join(result.stdout.split())


def test_sort_dry_run_allowed_while_lock_held(tmp_path: Path) -> None:
    library = _library(tmp_path)

    with _held(library):
        result = runner.invoke(app, ["sort", "--library", str(library), "--dry-run"])

    assert result.exit_code == 0, result.stdout
    assert "Would file: 1" in result.stdout


@pytest.mark.parametrize("command", [["reclassify"], ["audit"], ["config"], ["propose-categories"]])
def test_read_only_commands_allowed_while_lock_held(tmp_path: Path, command: list[str]) -> None:
    library = _library(tmp_path)

    with _held(library):
        result = runner.invoke(app, [*command, "--library", str(library)])

    assert result.exit_code == 0, result.stdout


def test_sort_releases_the_lock_when_it_finishes(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert not (library / _LOCK).exists()
    assert runner.invoke(app, ["sort", "--library", str(library)]).exit_code == 0  # and a second run is fine


def test_rollback_releases_the_lock_when_it_fails(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["rollback", "--library", str(library), "--job-id", "20260101-000000-abcdef"])

    assert result.exit_code == 1
    assert "No rollback job found" in " ".join(result.stdout.split())
    assert not (library / _LOCK).exists()


def test_sort_clears_a_lock_left_by_a_run_that_died(tmp_path: Path, dead_pid: int) -> None:
    library = _library(tmp_path)
    (library / _LOCK).write_text(
        json.dumps({"pid": dead_pid, "command": "sort", "started": "2026-10-12T09:30:00+11:00"}), encoding="utf-8"
    )

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "Filed: 1" in result.stdout
    assert not (library / _LOCK).exists()


def _leave_stale_lock(library: Path, dead_pid: int) -> None:
    """A lock as a `reclassify` run that died (killed, or the machine lost power) would have left it."""

    (library / _LOCK).write_text(
        json.dumps({"pid": dead_pid, "command": "reclassify", "started": "2026-10-12T09:30:00+11:00"}),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("command", "arguments"),
    [("sort", []), ("reclassify", ["--apply"]), ("rollback", ["--job-id", "20260101-000000-abcdef"])],
)
def test_changing_commands_warn_when_they_clear_a_stale_lock(
    tmp_path: Path, dead_pid: int, command: str, arguments: list[str]
) -> None:
    library = _library(tmp_path)
    _leave_stale_lock(library, dead_pid)

    result = runner.invoke(app, [command, "--library", str(library), *arguments])

    warning = " ".join(result.stderr.split())
    assert "cleared a stale run lock" in warning
    assert f"reclassify, process {dead_pid}, started 2026-10-12 09:30:00" in warning
    assert "cleared a stale run lock" in (library / _LOG_FILE).read_text(encoding="utf-8")


def test_stale_lock_warning_is_hidden_by_quiet_but_kept_in_the_log(tmp_path: Path, dead_pid: int) -> None:
    library = _library(tmp_path)
    _leave_stale_lock(library, dead_pid)

    result = runner.invoke(app, ["sort", "--library", str(library), "-q"])

    assert result.exit_code == 0, result.stdout
    assert "stale run lock" not in result.stderr  # -q shows errors only
    assert "cleared a stale run lock" in (library / _LOG_FILE).read_text(encoding="utf-8")


def test_sort_without_a_stale_lock_says_nothing_about_one(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "stale run lock" not in result.stderr  # the phrase, not the word: the library's path is in the log
    assert "stale run lock" not in (library / _LOG_FILE).read_text(encoding="utf-8")


def test_preview_leaves_a_stale_lock_alone_and_says_nothing(tmp_path: Path, dead_pid: int) -> None:
    # A preview takes no lock, so it neither clears the stale one nor has anything to report about it.
    library = _library(tmp_path)
    _leave_stale_lock(library, dead_pid)

    result = runner.invoke(app, ["sort", "--library", str(library), "--dry-run"])

    assert result.exit_code == 0, result.stdout
    assert "stale run lock" not in result.stderr
    assert (library / _LOCK).exists()


def test_sort_unreadable_lock_file_refused_and_left_alone(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / _LOCK).write_text("garbage", encoding="utf-8")

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 1
    assert "cannot be read" in " ".join(result.stdout.split())
    assert (library / _LOCK).read_text(encoding="utf-8") == "garbage"


def test_sort_bad_flags_fail_before_taking_the_lock(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["sort", "--library", str(library), "--keep-folders", "--keep-folders-off"])

    assert result.exit_code == 1
    assert not (library / _LOCK).exists()


# endregion


# region Logging options


_LOG_FILE = Path(".microfiche") / "microfiche.log"


def _handlers_left_on(logger_name: str) -> list[logging.Handler]:
    """The handlers on a logger other than the library's own quiet ``NullHandler``."""

    return [h for h in logging.getLogger(logger_name).handlers if not isinstance(h, logging.NullHandler)]


@pytest.mark.parametrize("command", ["sort", "reclassify", "propose-categories", "config", "audit"])
@pytest.mark.parametrize("flag", ["-v", "-q", "--verbose", "--quiet"])
def test_commands_verbose_and_quiet_flags_accepted(tmp_path: Path, command: str, flag: str) -> None:
    result = runner.invoke(app, [command, "--library", str(_library(tmp_path)), flag])

    assert result.exit_code == 0, result.stdout


def test_sort_records_start_in_log_file(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["sort", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert "sort: library" in (library / _LOG_FILE).read_text(encoding="utf-8")


def test_sort_dry_run_writes_no_log_file(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["sort", "--library", str(library), "--dry-run"])

    assert result.exit_code == 0, result.stdout
    assert not (library / _LOG_FILE).exists()


def test_reclassify_apply_records_start_in_log_file(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["reclassify", "--library", str(library), "--apply"])

    assert result.exit_code == 0, result.stdout
    assert "reclassify: library" in (library / _LOG_FILE).read_text(encoding="utf-8")


def test_reclassify_preview_writes_no_log_file(tmp_path: Path) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, ["reclassify", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert not (library / _LOG_FILE).exists()


@pytest.mark.parametrize("command", ["propose-categories", "config", "audit"])
def test_read_only_commands_write_no_log_file(tmp_path: Path, command: str) -> None:
    library = _library(tmp_path)

    result = runner.invoke(app, [command, "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    assert not (library / _LOG_FILE).exists()


def test_rollback_records_start_in_log_file(tmp_path: Path) -> None:
    library = _library(tmp_path)
    job_id = _sort(library)
    # Deleting the file also proves sort closed it: Windows will not delete a file that is still open.
    (library / _LOG_FILE).unlink()

    result = runner.invoke(app, ["rollback", "--library", str(library), "--job-id", job_id])

    assert result.exit_code == 0, result.stdout
    assert "rollback: library" in (library / _LOG_FILE).read_text(encoding="utf-8")


def test_rollback_invalid_config_works_without_log_file(tmp_path: Path) -> None:
    # The log file's settings live in the config, so with an invalid one there is no log file, but undo still works.
    library = _library(tmp_path)
    job_id = _sort(library)
    (library / _LOG_FILE).unlink()
    _break_config(library)

    result = runner.invoke(app, ["rollback", "--library", str(library), "--job-id", job_id])

    assert result.exit_code == 0, result.stdout
    assert not (library / _LOG_FILE).exists()


def test_sort_default_hides_start_line_on_screen(tmp_path: Path) -> None:
    result = runner.invoke(app, ["sort", "--library", str(_library(tmp_path))])

    assert "sort: library" not in result.stderr


def test_sort_verbose_shows_start_line_on_stderr(tmp_path: Path) -> None:
    result = runner.invoke(app, ["sort", "--library", str(_library(tmp_path)), "-v"])

    assert "sort: library" in result.stderr
    assert "sort: library" not in result.stdout  # stdout stays clean for piping


def test_sort_quiet_wins_over_verbose(tmp_path: Path) -> None:
    result = runner.invoke(app, ["sort", "--library", str(_library(tmp_path)), "-v", "-q"])

    assert result.exit_code == 0, result.stdout
    assert "sort: library" not in result.stderr


@pytest.mark.parametrize("command", ["sort", "config"])
def test_commands_leave_no_logging_handlers_behind(tmp_path: Path, command: str) -> None:
    # Otherwise one command's log file stays open, and the next invocation in this process writes to it.
    runner.invoke(app, [command, "--library", str(_library(tmp_path))])

    assert _handlers_left_on("core") == []
    assert _handlers_left_on("cli") == []


def test_sort_use_ai_openai_notice_stays_on_stdout_and_goes_to_log_file_only(
    tmp_path: Path, built_with: list[AIConfig]
) -> None:
    library = _library(tmp_path)
    _set_ai(library, 'provider = "openai"\n')

    result = runner.invoke(app, ["sort", "--library", str(library), "--use-ai"])

    assert "sent to OpenAI" in result.stdout  # the direct print stays
    assert "sent to OpenAI" not in result.stderr  # and the log does not repeat it on screen
    assert "sent to OpenAI" in (library / _LOG_FILE).read_text(encoding="utf-8")


def test_sort_use_ai_unlimited_notice_stays_on_stdout_and_goes_to_log_file_only(
    tmp_path: Path, built_with: list[AIConfig]
) -> None:
    library = _library(tmp_path)
    _set_ai(library, "max_document_chars = 0\n")

    result = runner.invoke(app, ["sort", "--library", str(library), "--use-ai"])

    assert "no limit" in result.stdout
    assert "no limit" not in result.stderr
    assert "no limit" in (library / _LOG_FILE).read_text(encoding="utf-8")


def test_sort_use_ai_openai_notice_survives_quiet(tmp_path: Path, built_with: list[AIConfig]) -> None:
    # A notice about what leaves the machine is a consent matter, so -q must not hide it.
    library = _library(tmp_path)
    _set_ai(library, 'provider = "openai"\n')

    result = runner.invoke(app, ["sort", "--library", str(library), "--use-ai", "-q"])

    assert "sent to OpenAI" in result.stdout


def test_sort_use_ai_provider_down_warning_is_in_log_file_and_hidden_by_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _library(tmp_path)
    monkeypatch.setattr("cli.commands.build_provider", lambda config: _DownProvider())

    result = runner.invoke(app, ["sort", "--library", str(library), "--use-ai", "-q"])

    assert result.exit_code == 0, result.stdout
    assert "AI fallback unavailable" not in result.stderr  # -q shows errors only
    assert "AI fallback unavailable" in (library / _LOG_FILE).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("command", "arguments"),
    [("sort", []), ("reclassify", ["--apply"]), ("rollback", ["--job-id", "20260101-000000-abcdef"])],
)
def test_refused_run_leaves_no_log_trace(tmp_path: Path, command: str, arguments: list[str]) -> None:
    # Only the run holding the lock may write the log file, so a run the lock refuses logs nothing at all,
    # on screen (even with -v) or in the file. It still says why on stdout.
    library = _library(tmp_path)

    with _held(library):
        result = runner.invoke(app, [command, "--library", str(library), "-v", *arguments])

    assert result.exit_code == 1
    assert f"{command}: library" not in result.stderr
    assert not (library / _LOG_FILE).exists()


def test_log_file_and_screen_never_hold_document_text(tmp_path: Path, built_with: list[AIConfig]) -> None:
    # Run every command that logs, with the most verbose settings and the AI on, over documents that carry a marker.
    marker = "UNIQUE-DOCUMENT-TEXT-MARKER"
    library = _library(tmp_path)
    (library / "_sorting" / "known.md").write_text(
        f"Project Phoenix architecture decisions. {marker}", encoding="utf-8"
    )
    (library / "_sorting" / "unknown.md").write_text(f"Nothing recognisable in here. {marker}", encoding="utf-8")

    sorted_ = runner.invoke(app, ["sort", "--library", str(library), "--use-ai", "-v"])
    job = _JOB_LINE.search(sorted_.stdout)
    assert job is not None, sorted_.stdout
    reclassified = runner.invoke(app, ["reclassify", "--library", str(library), "--apply", "-v"])
    rolled_back = runner.invoke(app, ["rollback", "--library", str(library), "--job-id", job.group(1), "-v"])

    log = (library / _LOG_FILE).read_text(encoding="utf-8")
    assert "known.md" in log  # something was logged, so the checks below are not trivially true
    for result in (sorted_, reclassified, rolled_back):
        assert result.exit_code == 0, result.stdout
        assert marker not in result.stderr
    assert marker not in log


# endregion


# region Progress


class _ProgressSpy:
    """Stands in for the progress bar: remembers how it was asked for, and every progress call it was handed."""

    def __init__(self) -> None:
        self.settings: list[dict[str, bool]] = []
        self.calls: list[tuple[int, int]] = []


@pytest.fixture
def progress_spy(monkeypatch: pytest.MonkeyPatch) -> _ProgressSpy:
    spy = _ProgressSpy()

    @contextmanager
    def fake_progress_bar(**settings: bool) -> Iterator[Callable[[int, int], None]]:
        spy.settings.append(settings)
        yield lambda done, total: spy.calls.append((done, total))

    monkeypatch.setattr("cli.commands.progress_bar", fake_progress_bar)
    return spy


def test_sort_reports_progress_through_the_bar(tmp_path: Path, progress_spy: _ProgressSpy) -> None:
    result = runner.invoke(app, ["sort", "--library", str(_library(tmp_path))])

    assert result.exit_code == 0, result.stdout
    assert progress_spy.settings == [{"quiet": False, "ai": False}]
    assert progress_spy.calls == [(0, 2), (1, 2), (2, 2)]


def test_sort_passes_use_ai_and_quiet_to_the_bar(
    tmp_path: Path, built_with: list[AIConfig], progress_spy: _ProgressSpy
) -> None:
    result = runner.invoke(app, ["sort", "--library", str(_library(tmp_path)), "--use-ai", "-q"])

    assert result.exit_code == 0, result.stdout
    assert progress_spy.settings == [{"quiet": True, "ai": True}]


def test_sort_dry_run_reports_progress_too(tmp_path: Path, progress_spy: _ProgressSpy) -> None:
    result = runner.invoke(app, ["sort", "--library", str(_library(tmp_path)), "--dry-run"])

    assert result.exit_code == 0, result.stdout
    assert progress_spy.calls[-1] == (2, 2)


def test_reclassify_reports_progress_through_the_bar(tmp_path: Path, progress_spy: _ProgressSpy) -> None:
    result = runner.invoke(app, ["reclassify", "--library", str(_library(tmp_path))])

    assert result.exit_code == 0, result.stdout
    assert progress_spy.settings == [{"quiet": False, "ai": False}]
    total = progress_spy.calls[0][1]
    assert total > 0
    assert progress_spy.calls == [(done, total) for done in range(total + 1)]


def test_sort_piped_output_carries_no_progress_control_codes(tmp_path: Path) -> None:
    # Under the test runner nothing is a terminal, as when output is piped or redirected.
    result = runner.invoke(app, ["sort", "--library", str(_library(tmp_path)), "-v"])

    assert result.exit_code == 0, result.stdout
    assert "\x1b" not in result.stderr  # no colour or cursor codes
    assert "\r" not in result.stderr  # no redraw of a bar
    assert "\r" not in result.stdout


# endregion


# region Filed bundles and a reduced depth


def test_reclassify_keeps_a_filed_bundle_whole(tmp_path: Path) -> None:
    library = _library(tmp_path, with_pack=True)
    runner.invoke(app, ["sort", "--library", str(library)])
    pack = library / "Project Phoenix" / "02 Architecture" / _PACK
    assert pack.is_dir()

    result = runner.invoke(app, ["reclassify", "--library", str(library), "--apply"])

    assert result.exit_code == 0, result.stdout
    assert pack.is_dir()
    assert (pack / "research-summary.md").is_file()  # not carried off to Research on its own


def test_reclassify_says_when_filed_items_sit_below_a_reduced_depth(tmp_path: Path) -> None:
    library = _library(tmp_path)
    runner.invoke(app, ["sort", "--library", str(library)])
    config = library / ".microfiche" / "microfiche-config.toml"
    config.write_text(config.read_text(encoding="utf-8").replace("depth = 2", "depth = 1"), encoding="utf-8")
    (library / _LIBRARY_FILE).write_text(json.dumps({"groups": []}), encoding="utf-8")

    result = runner.invoke(app, ["reclassify", "--library", str(library)])

    assert result.exit_code == 0, result.stdout
    output = " ".join(result.stdout.split())
    assert "1 filed item(s) sit in folders below the library's depth (1)" in output
    assert "no longer groups or categories" in output


def test_reclassify_says_nothing_about_depth_when_nothing_is_below_it(tmp_path: Path) -> None:
    library = _library(tmp_path)
    runner.invoke(app, ["sort", "--library", str(library)])

    result = runner.invoke(app, ["reclassify", "--library", str(library)])

    assert "below the library's depth" not in result.stdout


def test_reclassify_corrupt_ledger_exits_1_with_a_message(tmp_path: Path) -> None:
    library = _library(tmp_path)
    (library / ".microfiche" / "ledger.jsonl").write_text("not json\n", encoding="utf-8")

    result = runner.invoke(app, ["reclassify", "--library", str(library)])

    assert result.exit_code == 1
    assert "ledger" in result.stdout.lower()


# endregion
