"""The microfiche Typer application: registers every top-level command."""

from __future__ import annotations

import typer

from cli import commands

app = typer.Typer(name="microfiche", help="Organize project reference materials into a structured library.")
app.command(name="sort")(commands.sort)
app.command(name="review")(commands.review)
app.command(name="propose-categories")(commands.propose_categories)
app.command(name="resort")(commands.resort)
app.command(name="index")(commands.index)
app.command(name="audit")(commands.audit)
app.command(name="rollback")(commands.rollback)

__all__ = ["app"]
