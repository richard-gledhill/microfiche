"""Command implementations for the microfiche CLI. Registered onto the Typer app in cli.app."""

from __future__ import annotations

import functools
import logging
import signal
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Any, NoReturn, ParamSpec, TypeVar

import typer
from microfiche.cli.display import (
    render_ai_verification,
    render_config,
    render_library_sync,
    render_reclassify_result,
    render_reclassify_table,
    render_sort_report,
    render_watch_batch,
)
from microfiche.cli.init_prompts import ask_revert, render_changes, walk_through
from microfiche.cli.json_output import (
    ErrorOutput,
    audit_output,
    config_output,
    file_output,
    reclassify_output,
    review_queue_output,
    rollback_output,
    sort_output,
)
from microfiche.cli.logging import FILE_ONLY, configure_logging, reset_logging, stderr_console
from microfiche.cli.progress import progress_bar
from microfiche.cli.review import render_outcome, render_summary, stdin_is_terminal, work_queue
from microfiche.core.ai.base import AIProvider
from microfiche.core.ai.check import check_ai
from microfiche.core.ai.factory import build_provider
from microfiche.core.ai.llm_classifier import LLMClassifier
from microfiche.core.classifier import VerificationStats
from microfiche.core.config import CONFIG_FILENAME, AIConfig, ConfigError, ConfigProblem
from microfiche.core.drift import DriftItem, DriftReport, check_drift, find_modified, record_moves
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
from microfiche.core.library.library_file import LIBRARY_FILENAME
from microfiche.core.library.library_sync import sync_library_file
from microfiche.core.library_init import (
    BackupExistsError,
    ConfigChangedError,
    ConfigEditor,
    ConfigExistsError,
    InstallState,
    create_inbox,
    inspect_install,
    install_defaults,
    rebuild_library_file,
)
from microfiche.core.models.unit import SortableUnit
from microfiche.core.organizer import SortReport, run_sort
from microfiche.core.reclassify import ReclassifyProposal, apply_reclassification, items_below_depth, run_reclassify
from microfiche.core.review import ReviewError, ReviewOutcome, ReviewSession
from microfiche.core.runlock import LockHolder, RunLockError, run_lock
from microfiche.core.scanner import scan_sorting_inbox
from microfiche.core.watcher import WatchBatch, Watcher
from rich.console import Console
from rich.markup import escape

# region Constants and types

console = Console()
_logger = logging.getLogger(__name__)
_P = ParamSpec("_P")
_R = TypeVar("_R")
# Whether the running command was given --json: then `console` is the stderr one, and a failure is also a JSON document.
_json_active = False

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
_UNITS_ARGUMENT = typer.Argument(
    ...,
    help="The inbox documents or folders to file, named by their path inside the inbox (`review --list` shows them).",
)
_JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Print the result as one JSON document on stdout and nothing else there (messages and progress go to "
    "stderr). The shape is versioned and documented in schemas/.",
)


@contextmanager
def _json_mode(enabled: bool) -> Iterator[None]:
    """For the length of one command run with ``--json``, send messages to stderr and make failures JSON too.

    Rebinds the module's ``console`` (display functions are handed it at call time), so nothing but the JSON document
    reaches stdout. Restored afterwards, because the process may run several commands (the tests do).
    """

    global console, _json_active
    saved = console, _json_active
    if enabled:
        console, _json_active = stderr_console, True
    try:
        yield
    finally:
        console, _json_active = saved


def _json_command(function: Callable[_P, _R]) -> Callable[_P, _R]:
    """Run a command inside ``_json_mode`` when it was given ``--json`` (its ``as_json`` argument)."""

    @functools.wraps(function)
    def run(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        with _json_mode(bool(kwargs.get("as_json"))):
            return function(*args, **kwargs)

    return run


# endregion


# region Public API


@_json_command
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
        "classifications the rules engine can't resolve. Needs [ai] model set. Before any document is read, one "
        "test question (no document text) checks the AI answers; if it does not, nothing is moved and the "
        "command stops with the reason.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would be filed and what would need review, without moving or recording anything. "
        "Classification, including any --use-ai calls, runs as usual.",
    ),
    as_json: bool = _JSON_OPTION,
    verbose: bool = _VERBOSE_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """Classify and file what is in the inbox.

    Everything classified with enough confidence is filed as one job, which `rollback` can undo; the rest stays in the
    inbox for `review`.
    """

    if keep_folders and keep_folders_off:
        _fail("--keep-folders and --keep-folders-off contradict each other: pass only one.")
    opened = _open_library(library, uses_hints=True, needs_config=True)
    provider = _checked_ai_provider(opened.config.ai, quiet=quiet) if use_ai else None  # before the lock: see there
    with (
        _locked(
            opened, "sort", needed=not dry_run
        ) as cleared_lock,  # a preview only reads, so it runs beside a real run
        _logging(  # after the lock: see _logging
            "sort", opened, verbose=verbose, quiet=quiet, writes=not dry_run, cleared_lock=cleared_lock
        ),
        progress_bar(quiet=quiet, ai=use_ai) as on_progress,
    ):
        drift = _check_drift(opened, record=not dry_run)  # first: a bundle moved by hand changes the taxonomy
        ai_classifier = _build_ai_classifier(opened.config.ai, provider) if provider is not None else None
        report = run_sort(
            opened,
            keep_folders=_keep_folders_override(keep_folders, keep_folders_off),
            ai_classifier=ai_classifier,
            dry_run=dry_run,
            progress=on_progress,
        )
    if as_json:
        _emit(sort_output(report, opened, drift))
    else:
        render_sort_report(console, report)


@_json_command
def watch(
    library: Path = _LIBRARY_OPTION,
    interval: float | None = typer.Option(
        None,
        "--interval",
        help="Seconds between scans of the inbox, for this run. Defaults to [watch] interval_seconds (3600).",
    ),
    use_ai: bool = typer.Option(
        False,
        "--use-ai",
        help="Fall back to the AI named in the library's config, as `sort --use-ai` does. The test question is asked "
        "once, at the start; if the AI later fails, the rest of the run uses the rules only.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print one compact JSON line on stdout for each batch: the same document as `sort --json`, or "
        "an `error` line if the batch failed. Messages go to stderr.",
    ),
    verbose: bool = _VERBOSE_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """Keep the inbox filed: scan it on a timer and file what has stopped changing.

    Each scan only looks at file sizes and times, never at content. A document is filed once it is unchanged between two
    scans (so between one and two intervals after it arrives) and nothing else arrived or changed in the latest scan,
    so a folder copied in is filed as one job. Each batch is a normal `sort` of those documents: the same checks, and
    one job that `rollback` can undo. A document left for review is looked at again only when it changes or when the
    config or the library file does. Press Ctrl-C to stop: the batch in progress finishes first.
    """

    opened = _open_library(library, uses_hints=True, needs_config=True)
    seconds = interval if interval is not None else opened.config.watch.interval_seconds
    if seconds <= 0:
        _fail("--interval must be greater than 0.")
    provider = _checked_ai_provider(opened.config.ai, quiet=quiet) if use_ai else None
    ai_classifier = _build_ai_classifier(opened.config.ai, provider) if provider is not None else None

    def reopen() -> Library:
        fresh = Library(library)
        _ = fresh.config  # a config or library file that has gone bad is a failed scan, not the end of the run
        _ = fresh.library_file
        return fresh

    def run_batch(fresh: Library, entries: tuple[Path, ...]) -> tuple[SortReport, DriftReport]:
        return _watch_batch(fresh, entries, ai_classifier=ai_classifier, verbose=verbose, quiet=quiet)

    def on_batch(batch: WatchBatch) -> None:
        _report_watch_batch(batch, as_json=as_json, quiet=quiet)

    watcher = Watcher(reopen, run_batch, on_batch, interval=seconds)
    configure_logging(verbose=verbose, quiet=quiet)
    try:
        if not quiet:
            console.print(
                f"Watching {escape(str(opened.inbox))} every {seconds:g} s. Press Ctrl-C to stop.", soft_wrap=True
            )
        with _stop_on_interrupt(watcher):
            watcher.run()
    finally:
        reset_logging()
    if not quiet:
        console.print("Stopped watching.")


@_json_command
def review(
    library: Path = _LIBRARY_OPTION,
    list_queue: bool = typer.Option(
        False,
        "--list",
        help="Only list what `review` would ask about, with the classifier's best guess for each, and ask nothing. "
        "Works without a terminal.",
    ),
    use_ai: bool = typer.Option(
        False,
        "--use-ai",
        help="Ask the AI named in the library's config for a best guess where the rules have none, as `sort` does, "
        "including the test question first (see `sort --help`).",
    ),
    as_json: bool = _JSON_OPTION,
    verbose: bool = _VERBOSE_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """Decide where the leftover documents go.

    Works through the documents `sort` left in the inbox. For each one you can accept the best guess, pick a group and category (or plan a new folder), skip it, or quit.
    Nothing is moved while you answer. At the end you see what you chose and confirm once; the chosen documents are
    then filed as one job, which `rollback` can undo. Documents you skip stay in the inbox, and so do copies of
    documents already in the library. Needs a terminal, except with --list, which only prints the queue.
    """

    opened = _open_library(library, uses_hints=True)
    if as_json and not list_queue:
        _fail("--json needs --list: `review` itself asks questions, so there is nothing to print as JSON.")
    if list_queue:
        _list_queue(opened, use_ai=use_ai, as_json=as_json, verbose=verbose, quiet=quiet)
        return
    if not stdin_is_terminal():
        _fail("review asks questions, so it needs a terminal. Use `sort`, or file the documents by hand.")
    provider = _checked_ai_provider(opened.config.ai, quiet=quiet) if use_ai else None
    with _logging("review", opened, verbose=verbose, quiet=quiet, writes=False):
        _check_drift(opened, record=False)
        with progress_bar(quiet=quiet, ai=use_ai) as on_progress:
            ai_classifier = _build_ai_classifier(opened.config.ai, provider) if provider is not None else None
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


@_json_command
def file_units(
    units: list[str] = _UNITS_ARGUMENT,
    library: Path = _LIBRARY_OPTION,
    to: str = typer.Option(
        ...,
        "--to",
        help="Where they go, as a folder that already exists: `Group/Category`, or `Group` in a library of groups only "
        "(or for a group that has no categories, with [sorting] file_in_empty_groups).",
    ),
    as_json: bool = _JSON_OPTION,
    verbose: bool = _VERBOSE_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """File held inbox documents into a folder, without asking.

    Does what `review` does for the documents you name, from a script: the same checks (the folder exists, the name is
    free there, the document is not a copy of one already in the library, it has not changed), and the same single
    job, which `rollback` can undo. Only documents `sort` left for a decision can be filed. If any one is refused,
    nothing is moved and the exit code is 1.
    """

    opened = _open_library(library, uses_hints=True, needs_config=True)
    with (
        _logging("file", opened, verbose=verbose, quiet=quiet, writes=False),
        progress_bar(quiet=quiet, ai=False) as on_progress,
    ):
        _check_drift(opened, record=False)
        session = ReviewSession.start(opened, progress=on_progress)
    folders, decided, refused = _choose(session, units, to)
    if refused:
        if as_json:
            _emit(file_output(opened, folders, [], None, refused))
        else:
            for name, why in refused:
                console.print(f"[red]{escape(name)}[/red]: {escape(why)}", soft_wrap=True)
            console.print("Nothing was moved.")
        raise typer.Exit(code=1)
    with (
        _locked(opened, "file") as cleared_lock,
        _logging("file", opened, verbose=verbose, quiet=quiet, writes=True, cleared_lock=cleared_lock),
    ):
        outcome = session.commit()
    if as_json:
        _emit(file_output(opened, folders, decided, outcome, ()))
    else:
        render_outcome(console, outcome)
    if outcome.failed:
        raise typer.Exit(code=1)


def propose_categories(
    library: Path = _LIBRARY_OPTION, verbose: bool = _VERBOSE_OPTION, quiet: bool = _QUIET_OPTION
) -> None:
    """Suggest new category folder names.

    Looks at common terms across the documents in the inbox. Never creates folders - this only prints suggestions. Scoping to an existing library folder
    instead of the inbox isn't implemented yet.
    """
    opened = _open_library(library, needs_config=True)
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


def init(library: Path = _LIBRARY_OPTION, verbose: bool = _VERBOSE_OPTION, quiet: bool = _QUIET_OPTION) -> None:
    """Set up the library's configuration, or check it and change it.

    With no configuration in .microfiche/, writes the default one, asking nothing. With a valid one, offers to go
    through the settings one by one; with an invalid one, lists the problems and offers to revert only the invalid
    settings, or all of them, to the defaults. Changes are written only after you choose or confirm them, and the
    file as it was before the run is kept as microfiche-config.toml.bak. Then creates the inbox if it is missing and adds the library's folders to
    .microfiche/microfiche-library.json, as `config --sync` does. Never touches your folders or documents.
    """

    state_dir = Library(library).state_dir
    check = inspect_install(state_dir)
    terminal = stdin_is_terminal()
    if check.state is InstallState.MISSING:
        with _init_writing(library, verbose=verbose, quiet=quiet):
            try:
                path = install_defaults(state_dir)
            except ConfigExistsError as err:
                _fail(f"{err}: another run wrote it. Run init again to check it.")
            console.print(f"Wrote the default configuration to {escape(str(path))}.", soft_wrap=True)
        _finish_init(library, terminal=terminal, verbose=verbose, quiet=quiet)
        return
    reverted = check.state is InstallState.INVALID
    if reverted:
        console.print(f"[yellow]{escape(str(check.error))}[/yellow]", soft_wrap=True)
        if not terminal:
            _fail("Nothing was changed. Run `microfiche init` in a terminal to fix it.")
        _revert(library, state_dir, check.problems, verbose=verbose, quiet=quiet)
    else:
        console.print("The configuration is valid.")
    if terminal and typer.confirm("Go through the settings?", default=False):
        editor = ConfigEditor(state_dir)
        walk_through(console, editor)
        _save_edits(library, editor, backup=not reverted, verbose=verbose, quiet=quiet)
    _finish_init(library, terminal=terminal, verbose=verbose, quiet=quiet)


@_json_command
def config(
    library: Path = _LIBRARY_OPTION,
    sync: bool = typer.Option(
        False,
        "--sync",
        help="Instead of showing the configuration, add an entry to the library file for every folder that has "
        "none, and list entries whose folder is gone.",
    ),
    as_json: bool = _JSON_OPTION,
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
        _check_drift(opened, record=sync)
        if sync:
            result = sync_library_file(opened)
        elif as_json:
            _emit(config_output(opened.config, None))
        else:
            render_config(console, opened.config)
    if result is None:
        return
    if as_json:
        _emit(config_output(None, result))
        if result.write_error is not None:
            raise typer.Exit(code=1)
        return
    render_library_sync(console, result)
    if result.write_error is not None:
        raise typer.Exit(code=1)
    if not (result.added or result.missing):
        console.print("The library file already lists every folder.")


@_json_command
def reclassify(
    library: Path = _LIBRARY_OPTION,
    folder: Path | None = _FOLDER_OPTION,
    apply: bool = _APPLY_OPTION,
    use_ai: bool = typer.Option(
        False,
        "--use-ai",
        help="Use the AI named in the library's config as `sort --use-ai` does: for what the rules can't place, and "
        "to check rules answers scoring below [ai] verify_below. A document the AI disagrees with is left where it "
        "is. Needs [ai] model set; one test question (no document text) checks the AI answers first.",
    ),
    as_json: bool = _JSON_OPTION,
    verbose: bool = _VERBOSE_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """Re-check where filed documents belong.

    Reports where the classifier would file each already-filed document now. Without --apply this is a dry run. With --apply, the documents the table marks "move" are
    re-filed as one job (undo it with `rollback`); the rest are left exactly where they are.
    """

    lib = _open_library(library, uses_hints=True, needs_config=True)
    provider = _checked_ai_provider(lib.config.ai, quiet=quiet) if use_ai else None  # before the lock: see there
    ai_classifier = None
    with (
        _locked(
            lib, "reclassify", needed=apply
        ) as cleared_lock,  # held from planning to filing; the preview only reads
        _logging("reclassify", lib, verbose=verbose, quiet=quiet, writes=apply, cleared_lock=cleared_lock),
        progress_bar(quiet=quiet, ai=use_ai) as on_progress,
    ):
        drift = _check_drift(lib, record=apply)
        ai_classifier = _build_ai_classifier(lib.config.ai, provider) if provider is not None else None
        try:
            proposals = run_reclassify(lib, scope=folder, ai_classifier=ai_classifier, progress=on_progress)
        except ScopeOutsideLibraryError as err:
            _fail(str(err))
        except LedgerCorruptError as err:
            _fail(f"The ledger can't be read, so filed folders can't be told apart: {err}")
        _report_edits(drift, find_modified(lib, [proposal.current_path for proposal in proposals]))
        if not as_json:
            render_reclassify_table(console, proposals, root=lib.root, dry_run=not apply)
        if ai_classifier is not None:
            _describe_ai_use(proposals, ai_classifier, quiet_counts=as_json)
        result = apply_reclassification(lib, proposals) if apply else None
        below_depth = items_below_depth(lib)  # after any move, so it is what is still below
    depth = lib.config.library_structure.depth
    if as_json:
        _emit(
            reclassify_output(
                proposals,
                lib,
                dry_run=result is None,
                job=result.job if result else None,
                failed=result.failed if result else (),
                below_depth=below_depth,
                ai_unavailable=ai_classifier.failure if ai_classifier is not None else None,
                drift=drift,
            )
        )
        if result is not None and result.failed:
            raise typer.Exit(code=1)
        return
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


@_json_command
def audit(
    library: Path = _LIBRARY_OPTION,
    as_json: bool = _JSON_OPTION,
    verbose: bool = _VERBOSE_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """Show the audit log."""

    lib = Library(library)
    with _logging("audit", lib, verbose=verbose, quiet=quiet, writes=False):
        log_path = lib.state_dir / AUDIT_LOG_FILENAME
        if not log_path.exists():
            if as_json:
                _emit(audit_output(""))
                return
            console.print("[yellow]No audit log found yet.[/yellow]")
            return
        if as_json:
            _emit(audit_output(log_path.read_text(encoding="utf-8")))
            return
        # markup=False: audit lines contain file paths, and "[...]" in a name must not be read as markup.
        console.print(log_path.read_text(encoding="utf-8"), markup=False, highlight=False, soft_wrap=True)


@_json_command
def rollback(
    library: Path = _LIBRARY_OPTION,
    job_id: str | None = typer.Option(None, "--job-id", help="The id `sort` printed. Give this or --last."),
    last: bool = typer.Option(False, "--last", help="Undo the newest job that has not been undone."),
    as_json: bool = _JSON_OPTION,
    verbose: bool = _VERBOSE_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """Undo a filing job.

    Give the id `sort` printed, or use --last for the newest job that has not been undone.
    """

    if last == (job_id is not None):
        _fail("Give exactly one of --job-id and --last.")
    lib = Library(library)
    edited: list[str] = []
    drift = DriftReport()
    try:
        with (
            _locked(lib, "rollback") as cleared_lock,
            _logging("rollback", lib, verbose=verbose, quiet=quiet, writes=True, cleared_lock=cleared_lock),
        ):
            drift = _check_drift(lib, record=True)  # so a unit moved by hand is taken from where it is now
            # Resolved under the lock, so the job --last names is the one that is undone.
            job = rollback_job(lib, latest_job(lib.state_dir).job_id if last else str(job_id), edited=edited)
    except (JobNotFoundError, JobAlreadyRolledBackError, NoJobToRollBackError) as err:
        _fail(str(err))
    except JobMoveMissingError as err:
        _fail(
            f"{err}\nNothing was moved. Put the file(s) back where the message says, or restore them, and run it again."
        )
    except FileExistsError as err:
        _fail(
            f"{err}\nRollback stopped part-way; the moves already reversed are recorded. "
            "Fix the problem above and re-run the same command to finish."
        )
    if as_json:
        _emit(rollback_output(job, edited, drift))
        return
    for path in edited:
        console.print(
            f"[yellow]{escape(path)}[/yellow] had been edited since it was filed; moved back as it is.", soft_wrap=True
        )
    moves = sum(1 for event in job.moves if event.action == "move")
    restored = sum(1 for event in job.moves if event.action == "remove_folder")
    folders = f" and recreated {restored} emptied folder(s)" if restored else ""
    console.print(f"Reverted {moves} move(s){folders} from job {job.job_id}.", soft_wrap=True)


# endregion


# region Helpers


def _open_library(path: Path, *, uses_hints: bool = False, needs_config: bool = False) -> Library:
    """Open the library at ``path``, loading its config now so an invalid one stops the command up front.

    A command that classifies also loads the library file (the hints and filename rules), so a bad one
    stops it before anything is moved. Commands that never match on hints leave it unread. A command that
    ``needs_config`` stops when the library has no config file at all, rather than running on the defaults: it
    points to `init`, and writes nothing (no lock, no state folder).
    """

    library = Library(path)
    if needs_config and not (library.state_dir / CONFIG_FILENAME).is_file():
        _fail(
            f"No configuration found in {library.state_dir}. "
            f"Run `microfiche init --library {path}` to set the library up."
        )
    try:
        _ = library.config
        if uses_hints:
            _ = library.library_file
    except ConfigError as err:
        _fail(f"{err}\nRun `microfiche init --library {path}` to fix it.")
    return library


@contextmanager
def _init_writing(path: Path, *, verbose: bool, quiet: bool) -> Iterator[Library]:
    """Hold the run lock and log to the library's log file while `init` writes, yielding the library opened afresh."""

    library = Library(path)
    try:
        _ = library.config
        valid = True
    except ConfigError:  # being put right by this write; the log file's settings can't be trusted yet
        valid = False
    with (
        _locked(library, "init") as cleared_lock,
        _logging("init", library, verbose=verbose, quiet=quiet, writes=valid, cleared_lock=cleared_lock),
    ):
        yield library


def _revert(path: Path, state_dir: Path, problems: tuple[ConfigProblem, ...], *, verbose: bool, quiet: bool) -> None:
    """Ask how to put an invalid config right, and write the result. Exits if the person leaves it, or it is still wrong."""

    editor = ConfigEditor(state_dir)
    choice = ask_revert(console, can_keep_valid=editor.parsed and bool(problems))
    if choice == "leave":
        _fail("Nothing was changed.")
    if choice == "invalid":
        editor.revert_invalid(problems)
    else:
        editor.revert_all()
    remaining = editor.problems()
    if remaining:
        _fail("Reverting did not fix everything, so nothing was written:\n" + "\n".join(p.message for p in remaining))
    if not _write(path, editor, verbose=verbose, quiet=quiet):
        raise typer.Exit(code=1)


def _save_edits(path: Path, editor: ConfigEditor, *, backup: bool, verbose: bool, quiet: bool) -> None:
    """Show what the walk-through changed and write it once confirmed, keeping a backup if ``backup``."""

    changes = editor.changes()
    if not changes:
        console.print("Nothing changed.")
        return
    render_changes(console, changes)
    if not typer.confirm("Write these changes?", default=False):
        console.print("Nothing was written.")
        return
    if _write(path, editor, backup=backup, verbose=verbose, quiet=quiet) and any(
        change.key.startswith("ai.") for change in changes
    ):
        _offer_ai_test(path)


def _offer_ai_test(path: Path) -> None:
    """Offer to try the AI settings just saved. The check is the same one `--use-ai` makes; a failure only reports.

    Never automatic: a fresh install may have no Ollama or no ``ai`` extra, and with OpenAI it is a call to a
    hosted service the person has not asked for.
    """

    if not typer.confirm("\nTest the AI connection?", default=False):
        return
    try:
        result = check_ai(Library(path).config.ai)
    except ConfigError as err:
        console.print(f"[yellow]{escape(str(err))}[/yellow]", soft_wrap=True)
        return
    colour = "green" if result.ok else "yellow"
    label = "AI check passed" if result.ok else "The AI check failed"
    console.print(f"[{colour}]{label}: {escape(result.detail)}[/{colour}]", soft_wrap=True)


def _write(path: Path, editor: ConfigEditor, *, backup: bool = True, verbose: bool, quiet: bool) -> bool:
    """Write the edited config under the run lock. ``False`` if the person chose to keep an older backup.

    A second write in one run passes ``backup=False``: the backup the first one made holds the file as it was before
    the run, and is kept.
    """

    replace_backup = backup and editor.backup_path.exists()
    if replace_backup and not typer.confirm(f"Replace the older backup at {editor.backup_path}?", default=False):
        console.print("Nothing was written.")
        return False
    with _init_writing(path, verbose=verbose, quiet=quiet):
        try:
            kept = editor.save(replace_backup=replace_backup, backup=backup)
        except (ConfigChangedError, BackupExistsError) as err:
            _fail(str(err))
    kept_note = (
        f"the old file is kept as {kept}" if kept else f"the file as it was before is still in {editor.backup_path}"
    )
    console.print(f"Wrote {escape(str(editor.path))}; {escape(kept_note)}.", soft_wrap=True)
    return True


def _finish_init(path: Path, *, terminal: bool, verbose: bool, quiet: bool) -> None:
    """Create the inbox if it is missing and sync the library file, offering to rebuild one that can't be read."""

    unreadable: ConfigError | None = None
    with _init_writing(path, verbose=verbose, quiet=quiet) as library:
        inbox = create_inbox(library)
        if inbox is not None:
            console.print(f"Created the inbox {escape(str(inbox))}.", soft_wrap=True)
        try:
            result = sync_library_file(library)
        except ConfigError as err:
            unreadable = err
    if unreadable is not None:
        console.print(f"[yellow]{escape(str(unreadable))}[/yellow]", soft_wrap=True)
        if not terminal:
            _fail("The library file was left as it is. Fix it, or run `microfiche init` in a terminal.")
        if not typer.confirm(
            f"Rebuild it from the folders? The old file is kept as {LIBRARY_FILENAME}.bak.", default=False
        ):
            _fail("The library file was left as it is.")
        with _init_writing(path, verbose=verbose, quiet=quiet) as library:
            backup, result = rebuild_library_file(library)
        console.print(f"Moved the old library file to {escape(str(backup))}.", soft_wrap=True)
    render_library_sync(console, result)
    if result.write_error is not None:
        raise typer.Exit(code=1)
    if not (result.added or result.missing):
        console.print("The library file already lists every folder.")


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


def _checked_ai_provider(settings: AIConfig, *, quiet: bool) -> AIProvider:
    """Build the AI provider and prove it answers, before any document is classified; stop the command if not.

    Runs before the run lock is taken, so a slow or dead server never holds it, and before anything is moved.
    The call sends no document text. A failure is printed directly, so ``-q`` cannot hide it, with the fix where
    the provider knew one.
    """

    try:
        provider = build_provider(settings)
    except ConfigError as err:
        _fail(str(err))
    result = check_ai(settings, provider)
    if not result.ok:
        _fail(f"The AI check failed: {result.detail}")
    if not quiet:
        console.print(f"[dim]AI check passed: {escape(result.detail)}[/dim]", soft_wrap=True)
    return provider


def _build_ai_classifier(settings: AIConfig, provider: AIProvider) -> LLMClassifier:
    """Build the AI fallback from the library's ``[ai]`` settings, telling the user what it will do.

    Prints, once and before any document is classified, what the user would not otherwise know: that a
    hosted provider is sent the text of documents, and that an unlimited length costs tokens and time.
    """

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


def _describe_ai_use(
    proposals: list[ReclassifyProposal], ai_classifier: LLMClassifier, *, quiet_counts: bool = False
) -> None:
    """Say, once, what the AI did in a ``reclassify`` run: an unavailable AI, and the answers it checked.

    ``quiet_counts`` leaves the counts out, because the JSON document carries them.
    """

    if ai_classifier.failure is not None:
        console.print(f"[yellow]The AI fallback was unavailable ({escape(ai_classifier.failure)}).[/yellow]")
    if quiet_counts:
        return
    confirmed = sum(proposal.classification.confirmed_by_ai for proposal in proposals)
    overruled = sum(proposal.classification.ai_overruled for proposal in proposals)
    render_ai_verification(console, VerificationStats(confirmed + overruled, confirmed, overruled))


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
                _check_drift(library, record=True)
                return session.commit()
        except typer.Exit:
            if not typer.confirm("Try again?", default=False):
                raise


def _watch_batch(
    library: Library, entries: tuple[Path, ...], *, ai_classifier: LLMClassifier | None, verbose: bool, quiet: bool
) -> tuple[SortReport, DriftReport]:
    """File ``entries`` of the inbox as one job, holding the run lock only for as long as that takes.

    Waits up to ``[watch] lock_timeout_seconds`` for the lock; past that, ``RunLockedError`` ends the batch and
    ``watch`` tries again at the next scan. The log file is written only while the lock is held, then logging goes
    back to the screen alone.
    """

    try:
        with (
            run_lock(library, "watch", timeout=library.config.watch.lock_timeout_seconds) as cleared_lock,
            _logging("watch", library, verbose=verbose, quiet=quiet, writes=True, cleared_lock=cleared_lock),
        ):
            drift = _check_drift(library, record=True)
            report = run_sort(library, ai_classifier=ai_classifier, only=entries)
    finally:
        configure_logging(verbose=verbose, quiet=quiet)  # _logging reset it; between batches only the screen is used
    return report, drift


def _report_watch_batch(batch: WatchBatch, *, as_json: bool, quiet: bool) -> None:
    """Say how a batch went: a line on screen (a failure only, with ``-q``), and with ``--json`` one line on stdout."""

    when = datetime.now().strftime("%H:%M:%S")
    if batch.error is not None:
        console.print(f"[red]{when} Batch failed: {escape(batch.error)}[/red]", soft_wrap=True)
        if as_json:
            _emit_line(ErrorOutput(error=batch.error))
    elif batch.skipped is not None:
        if not quiet:
            console.print(
                f"[yellow]{when} Batch skipped; trying again at the next scan. {escape(batch.skipped)}[/yellow]",
                soft_wrap=True,
            )
    elif batch.report is not None and batch.library is not None:
        if not quiet:
            render_watch_batch(console, batch.report, when)
        if as_json:
            _emit_line(sort_output(batch.report, batch.library, batch.drift))


@contextmanager
def _stop_on_interrupt(watcher: Watcher) -> Iterator[None]:
    """Make the first Ctrl-C ask ``watcher`` to stop after its current batch; a second one interrupts as usual."""

    def handler(signum: int, frame: FrameType | None) -> None:
        if watcher.stopping:
            signal.default_int_handler(signum, frame)  # raises KeyboardInterrupt
        watcher.stop()
        console.print("Stopping after the current batch. Press Ctrl-C again to stop at once.")

    previous = signal.signal(signal.SIGINT, handler)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)


def _keep_folders_override(keep_folders: bool, keep_folders_off: bool) -> bool | None:
    """What the keep-folders options say for this run: on, off, or ``None`` to use the library's setting."""

    if keep_folders:
        return True
    return False if keep_folders_off else None


def _fail(message: str) -> NoReturn:
    """Print ``message`` as an error and exit with a non-zero status.

    With ``--json`` the message goes to stderr as usual and stdout gets an ``ErrorOutput``, so a script always reads
    one JSON document.
    """

    console.print(f"[red]{escape(message)}[/red]", soft_wrap=True)
    if _json_active:
        _emit(ErrorOutput(error=message))
    raise typer.Exit(code=1)


def _emit_line(output: Any) -> None:
    """Write ``output`` to stdout as one compact JSON line, for a command that prints a stream of them."""

    typer.echo(output.model_dump_json())


def _emit(output: Any) -> None:
    """Write ``output`` (a ``json_output`` model) to stdout as the command's one JSON document."""

    typer.echo(output.model_dump_json(indent=2))


def _check_drift(library: Library, *, record: bool) -> DriftReport:
    """Compare the ledger with the library and say, once, if filed units were moved, edited or removed by hand.

    With ``record`` (the command holds the run lock) the moved ones are written to the ledger so it points at their new
    places. Nothing is moved because of drift. The summary is a warning, so ``-q`` hides it; each item is logged.
    """

    try:
        report = check_drift(library)
    except LedgerCorruptError as err:  # the command that needs the ledger says so itself
        _logger.warning("drift check skipped: %s", err)
        return DriftReport()
    if record:
        record_moves(library, report)
    _announce(report)
    return report


def _report_edits(report: DriftReport, modified: list[DriftItem]) -> None:
    """Add the units found edited (by a command that read them anyway) to ``report`` and say so."""

    if modified:
        report.items.extend(modified)
        _announce(DriftReport(items=modified))


def _announce(report: DriftReport) -> None:
    if report.summary is None:
        return
    _logger.warning(report.summary)
    for item in report.items:
        place = f" -> {item.new_path}" if item.new_path else ""
        _logger.info("drift: %s %s%s", item.path, item.state.value, place)


def _choose(
    session: ReviewSession, names: list[str], destination: str
) -> tuple[tuple[str, ...] | None, list[SortableUnit], list[tuple[str, str]]]:
    """Choose ``destination`` for each of ``names`` in ``session``, refusing the ones that cannot go there.

    Returns:
        The folders the destination names (``None`` if it names none), the units chosen, and ``(name, reason)`` for each
        refusal. A destination that is not a place refuses every name with the same reason.
    """

    try:
        folders = session.place(destination)
    except ReviewError as err:
        return None, [], [(name, str(err)) for name in names]
    decided: list[SortableUnit] = []
    refused: list[tuple[str, str]] = []
    for name in names:
        try:
            item = session.item_named(name)
            problem = session.decide(item, folders)
        except ReviewError as err:
            refused.append((name, str(err)))
            continue
        if problem is not None:
            refused.append((name, problem))
        else:
            decided.append(item.unit)
    return folders, decided, refused


def _list_queue(opened: Library, *, use_ai: bool, as_json: bool, verbose: bool, quiet: bool) -> None:
    """Print what `review` would ask about, without asking: as JSON, or one line per unit."""

    provider = _checked_ai_provider(opened.config.ai, quiet=quiet) if use_ai else None
    with (
        _logging("review", opened, verbose=verbose, quiet=quiet, writes=False),
        progress_bar(quiet=quiet, ai=use_ai) as on_progress,
    ):
        drift = _check_drift(opened, record=False)
        ai_classifier = _build_ai_classifier(opened.config.ai, provider) if provider is not None else None
        session = ReviewSession.start(opened, ai_classifier=ai_classifier, progress=on_progress)
    if as_json:
        _emit(review_queue_output(session, opened, drift))
        return
    _describe_queue(session)
    if not session.items:
        console.print("Nothing to review: the inbox has no document waiting for a decision.")
    for item in session.items:
        guess = "/".join(item.suggestion) if item.suggestion else "no guess"
        console.print(f"{escape(item.name)}: {escape(guess)} ({escape(item.reason)})", soft_wrap=True)


# endregion
