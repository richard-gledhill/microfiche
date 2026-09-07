"""Smoke test that the microfiche CLI exposes all expected commands."""

from cli.app import app
from typer.testing import CliRunner

runner = CliRunner()


def test_app_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command_name in ["sort", "review", "propose-categories", "resort", "index", "audit", "rollback"]:
        assert command_name in result.stdout
