"""docs/cli-reference.md is generated from the Typer app; keep it from going stale."""

from __future__ import annotations

from pathlib import Path

from cli.app import app
from typer.cli import app as typer_cli
from typer.testing import CliRunner

_REFERENCE = Path(__file__).resolve().parents[2] / "docs" / "cli-reference.md"
_REGENERATE = "make docs-cli"

runner = CliRunner()


def test_cli_reference_matches_app(tmp_path: Path) -> None:
    generated = tmp_path / "cli-reference.md"
    result = runner.invoke(
        typer_cli,
        ["cli.app", "utils", "docs", "--name", "microfiche", "--title", "CLI reference", "--output", str(generated)],
    )

    assert result.exit_code == 0, result.output

    # Compare lines, not bytes: git may check the file out with CRLF line endings.
    assert _REFERENCE.read_text(encoding="utf-8").splitlines() == generated.read_text(encoding="utf-8").splitlines(), (
        f"docs/cli-reference.md is out of date with the CLI; run `{_REGENERATE}`"
    )


def test_stub_commands_say_not_implemented() -> None:
    for command in ("review", "index"):
        result = runner.invoke(app, [command, "--help"])

        assert result.exit_code == 0
        assert "Not implemented yet" in result.stdout
