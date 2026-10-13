"""microfiche CLI entry point."""

from __future__ import annotations

from microfiche.cli.app import app


def main() -> None:
    """Run the microfiche command line app."""

    app()
