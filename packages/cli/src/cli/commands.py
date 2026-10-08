"""Command implementations for the microfiche CLI. Registered onto the Typer app in cli.app."""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import typer
from core.ai.llm_classifier import LLMClassifier
from core.ai.ollama_provider import OllamaProvider
from core.config import ConfigError
from core.filer import (
    AUDIT_LOG_FILENAME,
    JobAlreadyRolledBackError,
    JobMoveMissingError,
    JobNotFoundError,
    rollback_job,
)
from core.library.category_suggester import suggest_categories
from core.library.library import Library, ScopeOutsideLibraryError
from core.organizer import run_sort
from core.reclassify import apply_reclassification, run_reclassify
from core.scanner import scan_sorting_inbox
from rich.console import Console
from rich.markup import escape

from cli.display import render_config, render_reclassify_result, render_reclassify_table, render_sort_report

console = Console()

_LIBRARY_OPTION = typer.Option(..., "--library", exists=True, file_okay=False, help="Path to the library root.")
_FOLDER_OPTION = typer.Option(None, "--folder", help="Limit to this folder; defaults to the whole library.")
_APPLY_OPTION = typer.Option(False, "--apply", help="Actually move files; without this it's a dry run.")
_SCOPE_OPTION = typer.Option(None, "--scope")


def sort(
    library: Path = _LIBRARY_OPTION,
    keep_folders: bool = typer.Option(
        False, "--keep-folders", help="Sort whole folders from the inbox intact, filed by dominant category."
    ),
    use_ai: bool = typer.Option(
        False, "--use-ai", help="Fall back to a local Ollama model for classifications the rules engine can't resolve."
    ),
) -> None:
    """Process the library's inbox: classify and file everything above the confidence threshold."""

    ai_classifier = LLMClassifier(OllamaProvider()) if use_ai else None
    report = run_sort(_open_library(library), keep_folders=keep_folders, ai_classifier=ai_classifier)
    render_sort_report(console, report)


def review() -> None:
    """Not implemented yet: work through the low-confidence review queue from the most recent sort run."""

    console.print("[yellow]The interactive review queue is not implemented yet - see cli/review.py.[/yellow]")
    raise typer.Exit(code=1)


def propose_categories(library: Path = _LIBRARY_OPTION) -> None:
    """Suggest new category folder names from common terms across documents in the sorting inbox.

    Never creates folders - this only prints suggestions. Scoping to an existing library folder
    instead of the inbox isn't implemented yet.
    """
    units = scan_sorting_inbox(_open_library(library), keep_folders=True)
    documents = [document for unit in units for document in unit.documents]
    suggestions = suggest_categories(documents)
    if not suggestions:
        console.print("[yellow]No suggestions - the sorting inbox is empty or has no supported documents.[/yellow]")
        return
    for suggestion in suggestions:
        console.print(
            f"[bold]{suggestion.name}[/bold] (score={suggestion.score}) — e.g. {', '.join(suggestion.example_documents)}"
        )


def config(library: Path = _LIBRARY_OPTION) -> None:
    """Library configuration."""

    render_config(console, _open_library(library).config)


def reclassify(
    library: Path = _LIBRARY_OPTION,
    folder: Path | None = _FOLDER_OPTION,
    apply: bool = _APPLY_OPTION,
) -> None:
    """Re-review already-filed documents and report where the classifier would file them now.

    Without --apply this is a dry run. With --apply, the documents the table marks "move" are
    re-filed as one job (undo it with `rollback`); the rest are left exactly where they are.
    """

    lib = _open_library(library)
    try:
        proposals = run_reclassify(lib, scope=folder)
    except ScopeOutsideLibraryError as err:
        _fail(str(err))
    render_reclassify_table(console, proposals, dry_run=not apply)
    if not apply:
        render_reclassify_result(console, proposals, job=None, dry_run=True)
        return
    try:
        job = apply_reclassification(lib, proposals)
    except FileExistsError as err:
        _fail(
            f"{err}\nSome files may already have been moved; they are recorded in the job and can be undone "
            "(see `microfiche audit` for the job id, then `microfiche rollback`)."
        )
    render_reclassify_result(console, proposals, job=job, dry_run=False)


def index(library: Path = _LIBRARY_OPTION, scope: Path | None = _SCOPE_OPTION) -> None:
    """Not implemented yet: force-regenerate Obsidian index.md files for a folder (or the whole library)."""

    console.print("[yellow]index regeneration is not wired up to a folder walk yet - see cli/commands.py.[/yellow]")
    raise typer.Exit(code=1)


def audit(library: Path = _LIBRARY_OPTION) -> None:
    """Show the audit log."""

    log_path = Library(library).state_dir / AUDIT_LOG_FILENAME
    if not log_path.exists():
        console.print("[yellow]No audit log found yet.[/yellow]")
        return
    # markup=False: audit lines contain file paths, and "[...]" in a name must not be read as markup.
    console.print(log_path.read_text(encoding="utf-8"), markup=False, highlight=False, soft_wrap=True)


def rollback(library: Path = _LIBRARY_OPTION, job_id: str = typer.Option(..., "--job-id")) -> None:
    """Undo a filing job by id (the id `sort` prints)."""

    try:
        job = rollback_job(Library(library), job_id)
    except (JobNotFoundError, JobAlreadyRolledBackError) as err:
        _fail(str(err))
    except (JobMoveMissingError, FileExistsError) as err:
        _fail(
            f"{err}\nRollback stopped part-way; the moves already reversed are recorded. "
            "Fix the problem above and re-run the same command to finish."
        )
    console.print(f"Reverted {len(job.moves)} move(s) from job {job_id}.", soft_wrap=True)


def _open_library(path: Path) -> Library:
    """Open the library at ``path``, loading its config now so an invalid one stops the command up front."""

    library = Library(path)
    try:
        _ = library.config
    except ConfigError as err:
        _fail(str(err))
    return library


def _fail(message: str) -> NoReturn:
    """Print ``message`` as an error and exit with a non-zero status."""

    console.print(f"[red]{escape(message)}[/red]", soft_wrap=True)
    raise typer.Exit(code=1)
