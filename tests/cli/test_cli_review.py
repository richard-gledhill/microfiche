"""Tests for the prompts and summaries of `microfiche review`, below the command itself."""

import shutil
from pathlib import Path

from microfiche.cli.review import render_outcome, render_summary
from microfiche.core.filer import FailedFiling
from microfiche.core.library.library import Library
from microfiche.core.models.job import Job
from microfiche.core.review import ReviewOutcome, ReviewSession
from rich.console import Console

# region Test helpers


_MOCK_LIBRARY = Path(__file__).resolve().parents[1] / "mock_library"
_SOLAR = "SolarConstructionNotes.md"


def _session(tmp_path: Path) -> ReviewSession:
    library = tmp_path / "library"
    shutil.copytree(_MOCK_LIBRARY, library)
    shutil.rmtree(library / "_sorting" / "phoenix-weekly-pack")
    return ReviewSession.start(Library(library))


def _console() -> Console:
    return Console(record=True, width=200, force_terminal=False)


def _text(console: Console) -> str:
    return " ".join(console.export_text(clear=False).split())


# endregion


# region Public API


# region render_outcome


def test_render_outcome_reports_units_that_stayed_and_why(tmp_path: Path) -> None:
    session = _session(tmp_path)
    console = _console()
    outcome = ReviewOutcome(job=None, failed=[FailedFiling(session.items[0].unit, "it is no longer in the inbox")])

    render_outcome(console, outcome)

    shown = _text(console)
    assert "Filed: 0" in shown
    assert f"{_SOLAR} stays in the inbox: it is no longer in the inbox" in shown
    assert "Job:" not in shown  # nothing was filed, so there is nothing to undo


def test_render_outcome_names_the_folders_it_created(tmp_path: Path) -> None:
    console = _console()
    outcome = ReviewOutcome(job=Job(job_id="20261013-000000-abc123"), created=[tmp_path / "Project Atlas"])

    render_outcome(console, outcome)

    shown = _text(console)
    assert "Created the folder Project Atlas" in shown
    assert "Job: 20261013-000000-abc123" in shown
    assert "Undo with: microfiche rollback --library <your library> --job-id 20261013-000000-abc123" in shown


# endregion


# region render_summary


def test_render_summary_lists_only_new_folders_that_a_choice_uses(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.add_folder((), "Project Atlas")
    session.add_folder((), "Unused Group")
    session.add_folder(("Project Atlas",), "01 Plans")
    session.decide(session.items[0], ("Project Atlas", "01 Plans"))
    console = _console()

    render_summary(console, session)

    shown = _text(console)
    assert "Ready to file 1 of 1 unit(s)" in shown
    assert f"{_SOLAR} -> Project Atlas/01 Plans" in shown
    assert "Project Atlas/01 Plans" in shown.split("New folders")[1]
    assert "Unused Group" not in shown


def test_render_summary_says_how_many_stay_in_the_inbox(tmp_path: Path) -> None:
    library = tmp_path / "library"
    shutil.copytree(_MOCK_LIBRARY, library)
    shutil.rmtree(library / "_sorting" / "phoenix-weekly-pack")
    (library / "_sorting" / "Another.md").write_text("Nothing recognisable here.", encoding="utf-8")
    session = ReviewSession.start(Library(library))
    session.decide(session.items[0], ("Project Phoenix", "03 Research"))
    console = _console()

    render_summary(console, session)

    assert "Ready to file 1 of 2 unit(s)" in _text(console)
    assert "1 unit(s) stay in the inbox." in _text(console)


# endregion


# endregion
