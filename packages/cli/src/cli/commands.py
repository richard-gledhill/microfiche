"""Command implementations for the microfiche CLI. Registered onto the Typer app in cli.app."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import NoReturn

import typer
from core.ai.factory import build_provider
from core.ai.llm_classifier import LLMClassifier
from core.config import AIConfig, ConfigError
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
from core.runlock import RunLockError, run_lock
from core.scanner import scan_sorting_inbox
from rich.console import Console
from rich.markup import escape

from cli.display import render_config, render_reclassify_result, render_reclassify_table, render_sort_report

# region Constants and types

console = Console()

_LIBRARY_OPTION = typer.Option(..., "--library", exists=True, file_okay=False, help="Path to the library root.")
_FOLDER_OPTION = typer.Option(None, "--folder", help="Limit to this folder; defaults to the whole library.")
_APPLY_OPTION = typer.Option(False, "--apply", help="Actually move files; without this it's a dry run.")
_SCOPE_OPTION = typer.Option(None, "--scope")

# endregion


# region Public API


def sort(
    library: Path = _LIBRARY_OPTION,
    keep_folders: bool = typer.Option(
        False,
        "--keep-folders",
        help="Sort whole folders from the inbox intact, filed by dominant category, for this run.",
    ),
    keep_folders_off: bool = typer.Option(
        False,
        "--keep-folders-off",
        help="File the documents inside inbox folders one by one for this run, and remove each folder once it is "
        "empty, whatever the library's keep_folders setting says.",
    ),
    use_ai: bool = typer.Option(
        False,
        "--use-ai",
        help="Fall back to the AI named in the library's config (Ollama unless it says otherwise) for "
        "classifications the rules engine can't resolve.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would be filed and what would need review, without moving or recording anything. "
        "Classification, including any --use-ai calls, runs as usual.",
    ),
) -> None:
    """Process the library's inbox: classify and file everything above the confidence threshold."""

    if keep_folders and keep_folders_off:
        _fail("--keep-folders and --keep-folders-off contradict each other: pass only one.")
    opened = _open_library(library, uses_hints=True)
    with _locked(opened, "sort", needed=not dry_run):  # a preview only reads, so it can run beside a real run
        ai_classifier = _build_ai_classifier(opened.config.ai) if use_ai else None
        report = run_sort(
            opened,
            keep_folders=_keep_folders_override(keep_folders, keep_folders_off),
            ai_classifier=ai_classifier,
            dry_run=dry_run,
        )
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
    units = scan_sorting_inbox(_open_library(library)).units
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

    lib = _open_library(library, uses_hints=True)
    with _locked(lib, "reclassify", needed=apply):  # held from planning to filing; the preview only reads
        try:
            proposals = run_reclassify(lib, scope=folder)
        except ScopeOutsideLibraryError as err:
            _fail(str(err))
        render_reclassify_table(console, proposals, dry_run=not apply)
        result = apply_reclassification(lib, proposals) if apply else None
    if result is None:
        render_reclassify_result(console, proposals, job=None, dry_run=True)
    else:
        render_reclassify_result(console, proposals, job=result.job, failed=result.failed, dry_run=False)


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

    lib = Library(library)
    try:
        with _locked(lib, "rollback"):
            job = rollback_job(lib, job_id)
    except (JobNotFoundError, JobAlreadyRolledBackError) as err:
        _fail(str(err))
    except (JobMoveMissingError, FileExistsError) as err:
        _fail(
            f"{err}\nRollback stopped part-way; the moves already reversed are recorded. "
            "Fix the problem above and re-run the same command to finish."
        )
    moves = sum(1 for event in job.moves if event.action == "move")
    restored = sum(1 for event in job.moves if event.action == "remove_folder")
    folders = f" and recreated {restored} emptied folder(s)" if restored else ""
    console.print(f"Reverted {moves} move(s){folders} from job {job_id}.", soft_wrap=True)


# endregion


# region Helpers


def _open_library(path: Path, *, uses_hints: bool = False) -> Library:
    """Open the library at ``path``, loading its config now so an invalid one stops the command up front.

    A command that classifies also loads the library file (the hints and filename rules), so a bad one
    stops it before anything is moved. Commands that never match on hints leave it unread.
    """

    library = Library(path)
    try:
        _ = library.config
        if uses_hints:
            _ = library.library_file
    except ConfigError as err:
        _fail(str(err))
    return library


@contextmanager
def _locked(library: Library, command: str, *, needed: bool = True) -> Iterator[None]:
    """Hold the library's run lock around the block, or exit with a message if another run holds it.

    Args:
        library: The library the command changes.
        command: The command's name, recorded in the lock so a refused run can say what is in progress.
        needed: Whether to take the lock at all. A command that only reads passes ``False``.
    """

    with ExitStack() as stack:
        if needed:
            try:
                stack.enter_context(run_lock(library, command))
            except RunLockError as err:
                _fail(str(err))
        yield


def _build_ai_classifier(settings: AIConfig) -> LLMClassifier:
    """Build the AI fallback from the library's ``[ai]`` settings, telling the user what it will do.

    Prints, once and before any document is classified, what the user would not otherwise know: that a
    hosted provider is sent the text of documents, and that an unlimited length costs tokens and time.
    """

    try:
        provider = build_provider(settings)
    except ConfigError as err:
        _fail(str(err))
    if settings.provider == "openai":
        console.print(
            "[yellow]AI provider is OpenAI: the text of each document it is asked about is sent to OpenAI.[/yellow]",
            soft_wrap=True,
        )
    if settings.max_document_chars == 0:
        billing = " OpenAI bills for the tokens used." if settings.provider == "openai" else ""
        console.print(
            "[yellow]max_document_chars = 0: there is no limit on how much of each document is sent to the AI. "
            "This uses more tokens and takes longer, and a document longer than the model's context window "
            f"may fail or be cut off.{billing}[/yellow]",
            soft_wrap=True,
        )
    return LLMClassifier(provider, settings)


def _keep_folders_override(keep_folders: bool, keep_folders_off: bool) -> bool | None:
    """What the keep-folders options say for this run: on, off, or ``None`` to use the library's setting."""

    if keep_folders:
        return True
    return False if keep_folders_off else None


def _fail(message: str) -> NoReturn:
    """Print ``message`` as an error and exit with a non-zero status."""

    console.print(f"[red]{escape(message)}[/red]", soft_wrap=True)
    raise typer.Exit(code=1)


# endregion
