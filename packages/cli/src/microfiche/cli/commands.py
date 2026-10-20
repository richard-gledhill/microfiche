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
from microfiche.cli.init_prompts import ask_revert, render_changes, walk_through
from microfiche.cli.logging import FILE_ONLY, configure_logging, reset_logging
from microfiche.cli.progress import progress_bar
from microfiche.cli.review import render_outcome, render_summary, stdin_is_terminal, work_queue
from microfiche.core.ai.factory import build_provider
from microfiche.core.ai.llm_classifier import LLMClassifier
from microfiche.core.config import CONFIG_FILENAME, AIConfig, ConfigError, ConfigProblem
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
    opened = _open_library(library, uses_hints=True, needs_config=True)
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

    lib = _open_library(library, uses_hints=True, needs_config=True)
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
    _write(path, editor, backup=backup, verbose=verbose, quiet=quiet)


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
