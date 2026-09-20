"""Command implementations for the microfiche CLI. Registered onto the Typer app in cli.app."""

from __future__ import annotations

from pathlib import Path

import typer
from core.ai.llm_classifier import LLMClassifier
from core.ai.ollama_provider import OllamaProvider
from core.config import load_config
from core.library.category_suggester import suggest_categories
from core.organizer import run_sort
from core.resort import run_resort
from core.rollback import rollback_job
from core.scanner import scan_sorting_inbox
from rich.console import Console

from cli.display import render_config, render_resort_table, render_sort_report

console = Console()

_LIBRARY_OPTION = typer.Option(..., "--library", exists=True, file_okay=False, help="Path to the library root.")
_FOLDER_OPTION = typer.Option(None, "--folder", help="Limit to this folder; defaults to the whole library.")
_APPLY_OPTION = typer.Option(False, "--apply", help="Actually move files; without this it's a dry run.")
_SCOPE_OPTION = typer.Option(None, "--scope")

# Dot-prefixed so Obsidian's file explorer hides them by default in a vault-backed library.
_CONFIG_DIRNAME = ".microfiche-config"
_LOGS_DIRNAME = ".microfiche-logs"


def sort(
    library: Path = _LIBRARY_OPTION,
    keep_folders: bool = typer.Option(
        False, "--keep-folders", help="Sort whole folders from the inbox intact, filed by dominant category."
    ),
    use_ai: bool = typer.Option(
        False, "--use-ai", help="Fall back to a local Ollama model for classifications the rules engine can't resolve."
    ),
) -> None:
    """Process the library's sorting/ inbox: classify and file everything above the confidence threshold."""

    config = load_config(library / _CONFIG_DIRNAME)
    ai_classifier = LLMClassifier(OllamaProvider()) if use_ai else None
    report = run_sort(library, config, keep_folders=keep_folders, ai_classifier=ai_classifier)
    render_sort_report(console, report)


def review() -> None:
    """Work through the low-confidence review queue from the most recent sort run."""

    console.print("[yellow]The interactive review queue is not implemented yet - see cli/review.py.[/yellow]")
    raise typer.Exit(code=1)


def propose_categories(library: Path = _LIBRARY_OPTION) -> None:
    """Suggest new category folder names from common terms across documents in the sorting inbox.

    Never creates folders - this only prints suggestions. Scoping to an existing library folder
    instead of the inbox isn't implemented yet.
    """

    units = scan_sorting_inbox(library, keep_folders=True)
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

    config = load_config(library / _CONFIG_DIRNAME)
    render_config(console, config)


def resort(
    library: Path = _LIBRARY_OPTION,
    folder: Path | None = _FOLDER_OPTION,
    apply: bool = _APPLY_OPTION,
) -> None:
    """Re-review already-filed documents and report where the classifier would file them now."""

    config = load_config(library / _CONFIG_DIRNAME)
    proposals = run_resort(library, config, scope=folder)
    render_resort_table(console, proposals)
    if apply:
        console.print("[yellow]--apply is not wired up to the filer yet - this was a dry run only.[/yellow]")


def index(library: Path = _LIBRARY_OPTION, scope: Path | None = _SCOPE_OPTION) -> None:
    """Force-regenerate Obsidian index.md files for a folder (or the whole library)."""

    console.print("[yellow]index regeneration is not wired up to a folder walk yet - see cli/commands.py.[/yellow]")
    raise typer.Exit(code=1)


def audit(library: Path = _LIBRARY_OPTION) -> None:
    """Show the audit log."""

    log_path = library / _LOGS_DIRNAME / "audit.log"
    if not log_path.exists():
        console.print("[yellow]No audit log found yet.[/yellow]")
        return
    console.print(log_path.read_text(encoding="utf-8"))


def rollback(library: Path = _LIBRARY_OPTION, job_id: str = typer.Option(..., "--job-id")) -> None:
    """Undo a filing job by id."""

    events = rollback_job(library / _LOGS_DIRNAME, job_id)
    console.print(f"Reverted {len(events)} move(s) from job {job_id}.")
