"""The microfiche Typer application: registers every top-level command."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

import typer
from microfiche.cli import commands

# region Constants and types

app = typer.Typer(
    name="microfiche",
    help="Organize project reference materials into a structured library.",
    rich_markup_mode="markdown",
)

# endregion


# region Public API


@app.callback()
def main_options(
    show_version: bool = typer.Option(
        False,
        "--version",
        callback=lambda value: _print_version(value),
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Options that apply to the program as a whole, before any command."""


# endregion

app.command(name="sort")(commands.sort)
app.command(name="review")(commands.review)
app.command(name="propose-categories")(commands.propose_categories)
app.command(name="reclassify")(commands.reclassify)
app.command(name="audit")(commands.audit)
app.command(name="rollback")(commands.rollback)
app.command(name="config")(commands.config)

__all__ = ["app"]


# region Helpers


def _print_version(requested: bool) -> None:
    """Print the installed version and exit, when ``--version`` was given.

    ``is_eager`` makes Click run this before it checks the rest of the command line, so ``--version`` works
    without a command and without ``--library``.
    """

    if not requested:
        return
    try:
        installed = version("cli")
    except PackageNotFoundError:  # run from a checkout that was never installed
        installed = "unknown"
    typer.echo(f"microfiche {installed}")
    raise typer.Exit()


# endregion
