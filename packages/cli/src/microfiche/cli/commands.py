"""Command implementations for the microfiche CLI. Registered onto the Typer app in cli.app."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import NoReturn

import typer
from microfiche.cli.display import (
    render_config,
    render_library_sync,
    render_reclassify_result,
    render_reclassify_table,
    render_sort_report,
)
from microfiche.cli.logging import FILE_ONLY, configure_logging, reset_logging
from microfiche.cli.progress import progress_bar
from microfiche.cli.review import render_outcome, render_summary, stdin_is_terminal, work_queue
from microfiche.core.ai.factory import build_provider
from microfiche.core.ai.llm_classifier import LLMClassifier
from microfiche.core.config import AIConfig, ConfigError
from microfiche.core.filer import (
    AUDIT_LOG_FILENAME,
    JobAlreadyRolledBackError,
    JobMoveMissingError,
    JobNotFoundError,
    NoJobToRollBackError,
    latest_job,
    rollback_job,
)
from microfiche.core.ledger import LedgerCorruptError
from microfiche.core.library.category_suggester import suggest_categories
from microfiche.core.library.library import Library, ScopeOutsideLibraryError
from microfiche.core.library.library_sync import sync_library_file
from microfiche.core.organizer import run_sort
from microfiche.core.reclassify import apply_reclassification, items_below_depth, run_reclassify
from microfiche.core.review import ReviewOutcome, ReviewSession
from microfiche.core.runlock import LockHolder, RunLockError, run_lock
from microfiche.core.scanner import scan_sorting_inbox
from rich.console import Console
from rich.markup import escape

# region Constants and types

console = Console()
_logger = logging.getLogger(__name__)

_VERBOSE_OPTION = typer.Option(
    False,
    "--verbose",
    "-v",
    help="Also show progress messages on screen, and record debugging detail in the log file.",
)
_QUIET_OPTION = typer.Option(False, "--quiet", "-q", help="Show errors only on screen. Wins over --verbose.")
_LIBRARY_OPTION = typer.Option(..., "--library", exists=True, file_okay=False, help="Path to the library root.")
_FOLDER_OPTION = typer.Option(None, "--folder", help="Limit to this folder; defaults to the whole library.")
_APPLY_OPTION = typer.Option(False, "--apply", help="Actually move files; without this it's a dry run.")

# endregion


# region Public API


def sort(
    library: Path = _LIBRARY_OPTION,
    keep_folders: bool = typer.Option(
        False,
        "--keep-folders",
        help="Sort whole folders from the inbox intact, filed under the group or category most of their documents belong to, for this run.",
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
    verbose: bool = _VERBOSE_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """Classify and file what is in the inbox.

    Everything classified with enough confidence is filed as one job, which `rollback` can undo; the rest stays in the
    inbox for `review`.
    """

    if keep_folders and keep_folders_off:
        _fail("--keep-folders and --keep-folders-off contradict each other: pass only one.")
    opened = _open_library(library, uses_hints=True)
    with (
        _locked(
            opened, "sort", needed=not dry_run
        ) as cleared_lock,  # a preview only reads, so it runs beside a real run
        _logging(  # after the lock: see _logging
            "sort", opened, verbose=verbose, quiet=quiet, writes=not dry_run, cleared_lock=cleared_lock
        ),
        progress_bar(quiet=quiet, ai=use_ai) as on_progress,
    ):
        ai_classifier = _build_ai_classifier(opened.config.ai) if use_ai else None
        report = run_sort(
            opened,
            keep_folders=_keep_folders_override(keep_folders, keep_folders_off),
            ai_classifier=ai_classifier,
            dry_run=dry_run,
            progress=on_progress,
        )
    render_sort_report(console, report)


def review(
    library: Path = _LIBRARY_OPTION,
    use_ai: bool = typer.Option(
        False,
        "--use-ai",
        help="Ask the AI named in the library's config for a best guess where the rules have none, as `sort` does.",
    ),
    verbose: bool = _VERBOSE_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """Decide where the leftover documents go.

    Works through the documents `sort` left in the inbox. For each one you can accept the best guess, pick a group and category (or plan a new folder), skip it, or quit.
    Nothing is moved while you answer. At the end you see what you chose and confirm once; the chosen documents are
    then filed as one job, which `rollback` can undo. Documents you skip stay in the inbox, and so do copies of
    documents already in the library. Needs a terminal.
    """

    opened = _open_library(library, uses_hints=True)
    if not stdin_is_terminal():
        _fail("review asks questions, so it needs a terminal. Use `sort`, or file the documents by hand.")
    with _logging("review", opened, verbose=verbose, quiet=quiet, writes=False):
        with progress_bar(quiet=quiet, ai=use_ai) as on_progress:
            ai_classifier = _build_ai_classifier(opened.config.ai) if use_ai else None
            session = ReviewSession.start(opened, ai_classifier=ai_classifier, progress=on_progress)
        _describe_queue(session)
        if not session.items:
            console.print("Nothing to review: the inbox has no document waiting for a decision.")
            return
        work_queue(console, session)
        if not session.decisions:
            console.print("Nothing was chosen, so nothing was moved.")
            return
        render_summary(console, session)
        if not typer.confirm("File these now?", default=True):
            console.print("Nothing was moved.")
            return
    render_outcome(console, _file_chosen(opened, session, verbose=verbose, quiet=quiet))


def propose_categories(
    library: Path = _LIBRARY_OPTION, verbose: bool = _VERBOSE_OPTION, quiet: bool = _QUIET_OPTION
) -> None:
    """Suggest new category folder names.

    Looks at common terms across the documents in the inbox. Never creates folders - this only prints suggestions. Scoping to an existing library folder
    instead of the inbox isn't implemented yet.
    """
    opened = _open_library(library)
    if opened.config.library_structure.depth == 1:
        console.print("[yellow]This library is flat (depth = 1): it has groups and no categories to propose.[/yellow]")
        return
    with _logging("propose-categories", opened, verbose=verbose, quiet=quiet, writes=False):
        units = scan_sorting_inbox(opened).units
        documents = [document for unit in units for document in unit.documents]
        suggestions = suggest_categories(documents)
    if not suggestions:
        console.print("[yellow]No suggestions - the sorting inbox is empty or has no supported documents.[/yellow]")
        return
    for suggestion in suggestions:
        console.print(
            f"[bold]{suggestion.name}[/bold] (score={suggestion.score}) — e.g. {', '.join(suggestion.example_documents)}"
        )


def config(
    library: Path = _LIBRARY_OPTION,
    sync: bool = typer.Option(
        False,
        "--sync",
        help="Instead of showing the configuration, add an entry to the library file for every folder that has "
        "none, and list entries whose folder is gone.",
    ),
    verbose: bool = _VERBOSE_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """Show the library's configuration.

    With --sync it instead brings the library file in step with the folders. --sync adds an entry, with no hints, to .microfiche/microfiche-library.json for each group and category folder
    that has none, creating the file if the library has none. It never changes or removes an entry, and never
    creates or removes a folder. An entry whose folder is gone is listed each time, and kept.
    """

    opened = _open_library(library, uses_hints=sync)
    result = None
    with (
        _locked(opened, "config", needed=sync) as cleared_lock,
        _logging("config", opened, verbose=verbose, quiet=quiet, writes=sync, cleared_lock=cleared_lock),
    ):
        if sync:
            result = sync_library_file(opened)
        else:
            render_config(console, opened.config)
    if result is None:
        return
    render_library_sync(console, result)
    if result.write_error is not None:
        raise typer.Exit(code=1)
    if not (result.added or result.missing):
        console.print("The library file already lists every folder.")


def reclassify(
    library: Path = _LIBRARY_OPTION,
    folder: Path | None = _FOLDER_OPTION,
    apply: bool = _APPLY_OPTION,
    verbose: bool = _VERBOSE_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """Re-check where filed documents belong.

    Reports where the classifier would file each already-filed document now. Without --apply this is a dry run. With --apply, the documents the table marks "move" are
    re-filed as one job (undo it with `rollback`); the rest are left exactly where they are.
    """

    lib = _open_library(library, uses_hints=True)
    with (
        _locked(
            lib, "reclassify", needed=apply
        ) as cleared_lock,  # held from planning to filing; the preview only reads
        _logging("reclassify", lib, verbose=verbose, quiet=quiet, writes=apply, cleared_lock=cleared_lock),
        progress_bar(quiet=quiet, ai=False) as on_progress,
    ):
        try:
            proposals = run_reclassify(lib, scope=folder, progress=on_progress)
        except ScopeOutsideLibraryError as err:
            _fail(str(err))
        except LedgerCorruptError as err:
            _fail(f"The ledger can't be read, so filed folders can't be told apart: {err}")
        render_reclassify_table(console, proposals, root=lib.root, dry_run=not apply)
        result = apply_reclassification(lib, proposals) if apply else None
        below_depth = items_below_depth(lib)  # after any move, so it is what is still below
    depth = lib.config.library_structure.depth
    render_reclassify_result(
        console,
        proposals,
        root=lib.root,
        job=result.job if result else None,
        failed=result.failed if result else (),
        dry_run=result is None,
        below_depth=below_depth,
        depth=depth,
    )


def audit(library: Path = _LIBRARY_OPTION, verbose: bool = _VERBOSE_OPTION, quiet: bool = _QUIET_OPTION) -> None:
    """Show the audit log."""

    lib = Library(library)
    with _logging("audit", lib, verbose=verbose, quiet=quiet, writes=False):
        log_path = lib.state_dir / AUDIT_LOG_FILENAME
        if not log_path.exists():
            console.print("[yellow]No audit log found yet.[/yellow]")
            return
        # markup=False: audit lines contain file paths, and "[...]" in a name must not be read as markup.
        console.print(log_path.read_text(encoding="utf-8"), markup=False, highlight=False, soft_wrap=True)


def rollback(
    library: Path = _LIBRARY_OPTION,
    job_id: str | None = typer.Option(None, "--job-id", help="The id `sort` printed. Give this or --last."),
    last: bool = typer.Option(False, "--last", help="Undo the newest job that has not been undone."),
    verbose: bool = _VERBOSE_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """Undo a filing job.

    Give the id `sort` printed, or use --last for the newest job that has not been undone.
    """

    if last == (job_id is not None):
        _fail("Give exactly one of --job-id and --last.")
    lib = Library(library)
    try:
        with (
            _locked(lib, "rollback") as cleared_lock,
            _logging("rollback", lib, verbose=verbose, quiet=quiet, writes=True, cleared_lock=cleared_lock),
        ):
            # Resolved under the lock, so the job --last names is the one that is undone.
            job = rollback_job(lib, latest_job(lib.state_dir).job_id if last else str(job_id))
    except (JobNotFoundError, JobAlreadyRolledBackError, NoJobToRollBackError) as err:
        _fail(str(err))
    except (JobMoveMissingError, FileExistsError) as err:
        _fail(
            f"{err}\nRollback stopped part-way; the moves already reversed are recorded. "
            "Fix the problem above and re-run the same command to finish."
        )
    moves = sum(1 for event in job.moves if event.action == "move")
    restored = sum(1 for event in job.moves if event.action == "remove_folder")
    folders = f" and recreated {restored} emptied folder(s)" if restored else ""
    console.print(f"Reverted {moves} move(s){folders} from job {job.job_id}.", soft_wrap=True)


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
def _logging(
    command: str,
    library: Library,
    *,
    verbose: bool,
    quiet: bool,
    writes: bool,
    cleared_lock: LockHolder | None = None,
) -> Iterator[None]:
    """Set up logging for a command that has opened ``library``, and record that the command started.

    A command that changes the library enters this inside ``_locked``, not outside it. Only the run holding the
    lock may write the log file, so a run the lock refuses leaves no trace in it (nor on screen). The order also
    gives the lock a way to be heard: it is taken before logging exists, so it hands over what it did, and this
    logs it.

    Args:
        command: The command's name, written to the log's first line.
        library: The library the command works on.
        verbose: ``-v``: show progress messages too, and record debugging detail in the log file.
        quiet: ``-q``: show errors only on screen. Wins over ``verbose``.
        writes: Whether the command holds the run lock, and so also records to the library's log file. A preview
            or a read-only command passes ``False`` and leaves no log file behind.
        cleared_lock: The holder of the stale lock that ``_locked`` cleared to take its own, if it did. That run
            died without letting go, which is worth a warning.
    """

    try:
        configure_logging(verbose=verbose, quiet=quiet, library=library if writes else None)
    except ConfigError:
        # rollback must still work with an invalid config, so log to the screen only
        configure_logging(verbose=verbose, quiet=quiet)
        _logger.warning("Not writing a log file: the library's config can't be read")
    _logger.info("%s: library %s", command, library.root)
    if cleared_lock is not None:
        _logger.warning(
            "cleared a stale run lock left by a run that did not finish (%s, process %d, started %s)",
            cleared_lock.command,
            cleared_lock.pid,
            f"{cleared_lock.started:%Y-%m-%d %H:%M:%S}",
        )
    try:
        yield
    finally:
        reset_logging()


@contextmanager
def _locked(library: Library, command: str, *, needed: bool = True) -> Iterator[LockHolder | None]:
    """Hold the library's run lock around the block, or exit with a message if another run holds it.

    Args:
        library: The library the command changes.
        command: The command's name, recorded in the lock so a refused run can say what is in progress.
        needed: Whether to take the lock at all. A command that only reads passes ``False``.

    Yields:
        The holder of the stale lock that was cleared to take this one, or ``None`` if there was none (or no
        lock was needed). The caller logs it once logging is set up, which this cannot do: it comes first.
    """

    cleared: LockHolder | None = None
    with ExitStack() as stack:
        if needed:
            try:
                cleared = stack.enter_context(run_lock(library, command))
            except RunLockError as err:
                _fail(str(err))
        yield cleared


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
        notice = "AI provider is OpenAI: the text of each document it is asked about is sent to OpenAI."
        console.print(f"[yellow]{notice}[/yellow]", soft_wrap=True)
        _logger.warning(notice, extra=FILE_ONLY)
    if settings.max_document_chars == 0:
        billing = " OpenAI bills for the tokens used." if settings.provider == "openai" else ""
        notice = (
            "max_document_chars = 0: there is no limit on how much of each document is sent to the AI. "
            "This uses more tokens and takes longer, and a document longer than the model's context window "
            f"may fail or be cut off.{billing}"
        )
        console.print(f"[yellow]{notice}[/yellow]", soft_wrap=True)
        _logger.warning(notice, extra=FILE_ONLY)
    return LLMClassifier(provider, settings)


def _describe_queue(session: ReviewSession) -> None:
    """Say what `review` will not ask about, and why: copies, documents `sort` would file, an unavailable AI."""

    if session.duplicates:
        console.print(
            f"[dim]{len(session.duplicates)} document(s) are copies of other documents and stay in the inbox; "
            "`sort` lists them.[/dim]",
            soft_wrap=True,
        )
    if session.waiting:
        console.print(
            f"[dim]{session.waiting} document(s) are confident enough for `sort` to file, so `review` does not "
            "ask about them.[/dim]",
            soft_wrap=True,
        )
    if session.ai_unavailable is not None:
        console.print(f"[yellow]The AI fallback was unavailable ({escape(session.ai_unavailable)}).[/yellow]")


def _file_chosen(library: Library, session: ReviewSession, *, verbose: bool, quiet: bool) -> ReviewOutcome:
    """File the choices under the run lock, which is taken only now.

    Asking is read-only, and holding the lock meanwhile would stop `sort` for as long as the person takes. If another
    run holds it, the choices are kept and the person is asked whether to try again, rather than made all over again.
    """

    while True:
        try:
            with (
                _locked(library, "review") as cleared_lock,
                _logging("review", library, verbose=verbose, quiet=quiet, writes=True, cleared_lock=cleared_lock),
            ):
                return session.commit()
        except typer.Exit:
            if not typer.confirm("Try again?", default=False):
                raise


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
