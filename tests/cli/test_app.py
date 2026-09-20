"""Smoke test that the microfiche CLI exposes all expected commands."""

from pathlib import Path

from cli.app import app
from typer.testing import CliRunner

runner = CliRunner()


def test_app_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command_name in ["sort", "review", "propose-categories", "resort", "index", "audit", "rollback", "config"]:
        assert command_name in result.stdout


def test_config_command_shows_defaults_for_an_unconfigured_library(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "--library", str(tmp_path)])

    assert result.exit_code == 0
    assert "2" in result.stdout  # library_structure.depth default
    assert "suggest" in result.stdout  # obsidian.tag_mode default
