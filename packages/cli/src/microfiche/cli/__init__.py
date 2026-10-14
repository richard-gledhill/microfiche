"""microfiche CLI entry point."""

from __future__ import annotations

from microfiche.cli.app import app
from microfiche.cli.streams import prepare_output_streams


def main() -> None:
    """Run the microfiche command line app."""

    prepare_output_streams()
    app()
