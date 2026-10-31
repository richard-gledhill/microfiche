"""Files classified units into the library, records every move, and can undo a whole run.

One run of filing is a *job*. For each unit it moves, ``file_batch`` writes to three places under
the library's ``.microfiche/`` folder:

- ``rollback/job_<id>.json`` - the moves, so ``rollback_job`` can reverse them;
- ``ledger.jsonl`` - what each unit is, where it went, and why (see ``microfiche.core.ledger``);
- ``audit.log`` - one human-readable line per move, shown by ``microfiche audit``.

Nothing is ever deleted: rollback moves units back, and the ledger and audit log only grow. The one
thing removed is an inbox folder that is left completely empty once its files are filed; the removal is
recorded in the job so rollback recreates it.

A move is a plain rename (see ``microfiche.core.utils.filesystem.safe_move``), so it either happens or changes
nothing. A unit that cannot be moved, such as a file another program has open, stays where it is and
is reported back; it never stops the rest of the batch.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from microfiche.core.ledger import Ledger
from microfiche.core.library.library import Library
from microfiche.core.library.naming import apply_naming_rules
from microfiche.core.models.audit_event import AuditEvent
from microfiche.core.models.classification import ClassificationResult
from microfiche.core.models.job import Job
from microfiche.core.models.ledger import LedgerRecord
from microfiche.core.models.unit import SortableUnit
from microfiche.core.utils.errors import describe_error
from microfiche.core.utils.filesystem import is_link, safe_move
from microfiche.core.utils.hashing import unit_hash

# region Constants and types

AUDIT_LOG_FILENAME = "audit.log"
_ROLLBACK_DIRNAME = "rollback"
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# Windows error codes for a file another program has open: a sharing violation and a lock violation.
_FILE_IN_USE_WINERRORS = (32, 33)

_logger = logging.getLogger(__name__)


@dataclass
class FailedFiling:
    """A unit that could not be moved, and why. It is exactly where it was; nothing was recorded for it.

    Attributes:
        unit: The unit that stayed where it was.
        reason: One line a person can read, such as "it is open in another program; close it and sort again".
    """

    unit: SortableUnit
    reason: str


@dataclass
class FilingResult:
    """What ``file_batch`` did.

    Attributes:
        job: The saved job, or ``None`` if no unit was moved (nothing is written in that case).
        failed: The units that could not be moved. The rest of the batch was filed regardless.
    """

    job: Job | None = None
    failed: list[FailedFiling] = field(default_factory=list)


# endregion


# region Errors


class UnresolvedClassificationError(ValueError):
    """Raised when asked to file a unit whose group or category is unresolved.

    Callers must route unresolved classifications to the review queue instead of filing them.
    """

    def __init__(self, unit_name: str) -> None:
        self.unit_name = unit_name
        super().__init__(f"Cannot file '{unit_name}': it has no group, or no category where the library has them")


class JobNotFoundError(FileNotFoundError):
    """Raised when no rollback job exists for the requested job id."""

    def __init__(self, job_id: str, job_path: Path) -> None:
        self.job_id = job_id
        super().__init__(f"No rollback job found for id '{job_id}' at {job_path}")


class JobAlreadyRolledBackError(RuntimeError):
    """Raised when asked to roll back a job that has already been rolled back."""

    def __init__(self, job_id: str, rolled_back_at: datetime) -> None:
        self.job_id = job_id
        super().__init__(f"Job '{job_id}' was already rolled back at {rolled_back_at.isoformat(timespec='seconds')}")


class NoJobToRollBackError(LookupError):
    """Raised when the library has no job that is still waiting to be rolled back.

    Attributes:
        unreadable: The job files that could not be read, which are why a job may be missing.
    """

    def __init__(self, state_dir: Path, unreadable: Sequence[Path] = ()) -> None:
        self.unreadable = list(unreadable)
        message = f"No job to roll back: {state_dir / _ROLLBACK_DIRNAME} holds no job that is still applied"
        if self.unreadable:
            names = ", ".join(path.name for path in self.unreadable)
            message += f". {len(self.unreadable)} job file(s) could not be read ({names}); fix or remove them"
        super().__init__(message)


class JobMoveMissingError(FileNotFoundError):
    """Raised when a move can't be reversed because the file is at neither its old nor new location."""

    def __init__(self, event: AuditEvent, all_missing: Sequence[AuditEvent] = ()) -> None:
        self.event = event
        self.all_missing = tuple(all_missing) or (event,)
        gone = "; ".join(f"'{e.new_path}' is gone and '{e.original_path}' does not exist" for e in self.all_missing)
        super().__init__(f"Cannot roll back: {gone}")


# endregion


# region Public API


def file_batch(library: Library, items: list[tuple[SortableUnit, ClassificationResult]]) -> FilingResult:
    """Move each unit into its classified folder (group, then category if the library has them) and record a job.

    The whole batch is checked for unresolved classifications before anything moves. A move that
    then fails (a file another program has open, a destination taken in the meantime, a permission
    error) is nothing more than that unit staying where it is: moves are plain renames, so a failed
    one changes nothing. It is not recorded as a move, it is returned in ``failed`` with the reason,
    and the rest of the batch is filed. The job holds only the moves that happened, so they can be
    rolled back.

    Each unit's name is rewritten by the library's naming rules as it is filed.

    A unit taken out of an inbox folder (``SortableUnit.origin_folder``) may leave that folder empty.
    Once every unit is filed, such a folder is removed - with its empty sub-folders - if nothing at all
    is left inside it, and each removal is recorded in the job. A folder that still holds a file stays.

    Args:
        library: The library to file into.
        items: Pairs of a unit and its (resolved) classification.

    Returns:
        The saved job (``None`` if nothing was moved, in which case nothing is written) and the
        units that could not be moved.

    Raises:
        UnresolvedClassificationError: if any classification is unresolved (see ``ClassificationResult.folders``).
    """

    result = FilingResult()
    if not items:
        return result
    for unit, classification in items:
        if classification.folders is None:
            raise UnresolvedClassificationError(unit.source_path.name)

    state_dir = library.state_dir
    ledger = Ledger(state_dir)
    job = Job(job_id=_new_job_id())
    moved: list[SortableUnit] = []
    try:
        for unit, classification in items:
            try:
                event, record = _file_unit(unit, classification, library, job.job_id)
            except OSError as err:
                reason = _describe_move_failure(err)
                result.failed.append(FailedFiling(unit, reason))
                _logger.warning("could not move %s: %s", unit.source_path.name, reason)
                continue
            moved.append(unit)
            job.moves.append(event)
            ledger.append([record])
            _append_audit_lines(library, job.job_id, [event])
        _remove_emptied_folders(library, job, moved)
    finally:
        if job.moves:
            save_job(state_dir, job)
    result.job = job if job.moves else None
    if result.job is not None:
        _logger.info("filed %d unit(s) as job %s", len(moved), job.job_id)
    return result


def rollback_job(library: Library, job_id: str, *, edited: list[str] | None = None) -> Job:
    """Reverse every move of a job, newest first, and mark the job as rolled back.

    A folder the job removed once it was empty is recreated first, so the units that were in it can go back.

    A unit that was moved by hand since the job (the ledger has a ``relocated`` record for it) is taken from where it is
    now. One that is gone from both its filed and its original place stops the rollback before anything is moved, naming
    every such unit. One whose content differs from what was filed is moved back like any other; ``edited`` lists it.

    Safe to retry: if an earlier attempt stopped part-way, moves that were already reversed are
    recognised (the unit is back at its original location) and skipped.

    Args:
        library: The library the job was run on.
        job_id: The id printed by ``sort`` (the ``job_<id>.json`` file name without its decoration).
        edited: If given, receives the library-relative filed path of each unit moved back whose content had changed.

    Returns:
        The job, with ``rolled_back_at`` set.

    Raises:
        JobNotFoundError: if there is no such job.
        JobAlreadyRolledBackError: if the job was already rolled back.
        JobMoveMissingError: if a unit is at neither its original nor its filed location.
        FileExistsError: if something now occupies a unit's original location.
    """

    state_dir = library.state_dir
    job = load_job(state_dir, job_id)
    if job.rolled_back_at is not None:
        raise JobAlreadyRolledBackError(job.job_id, job.rolled_back_at)
    _logger.info("rolling back job %s: %d recorded step(s)", job.job_id, len(job.moves))

    ledger = Ledger(state_dir)
    relocations = ledger.relocations()
    filed_hashes = {r.path: r.content_hash for r in ledger.read_all() if r.event == "filed" and r.job_id == job.job_id}

    gone = _unreachable(library, job, relocations)
    if gone:
        raise JobMoveMissingError(gone[0], gone)

    reversed_events: list[AuditEvent] = []
    records: list[LedgerRecord] = []
    try:
        for event in reversed(job.moves):
            if event.action == "remove_folder":
                if not event.original_path.exists():  # already recreated by an earlier, interrupted rollback
                    event.original_path.mkdir(parents=True)
                    _logger.debug("recreated folder %s", library.relative(event.original_path))
                    reversed_events.append(AuditEvent(original_path=event.original_path, action="restore_folder"))
                continue
            if event.action != "move" or event.new_path is None:
                continue
            hops = _places(library, event, relocations)
            source = library.root / hops[-1]
            if not source.exists():
                if event.original_path.exists():
                    _logger.debug("already back: %s", library.relative(event.original_path))
                    continue  # already put back by an earlier, interrupted rollback
                raise JobMoveMissingError(event)
            content_hash = unit_hash(source)
            unit_type: Literal["file", "folder"] = "folder" if source.is_dir() else "file"
            _note_if_edited(filed_hashes.get(hops[0]), content_hash, hops, edited)
            safe_move(source, event.original_path)
            _logger.debug("moved back %s -> %s", hops[-1], library.relative(event.original_path))
            reversed_events.append(AuditEvent(original_path=source, new_path=event.original_path, action="rollback"))
            records.extend(
                LedgerRecord(
                    event="rolled_back",
                    job_id=job.job_id,
                    path=hop,
                    original_path=library.relative(event.original_path),
                    content_hash=content_hash,
                    unit_type=unit_type,
                )
                for hop in hops
            )
    finally:
        Ledger(state_dir).append(records)
        _append_audit_lines(library, job.job_id, reversed_events)

    job.rolled_back_at = datetime.now()
    save_job(state_dir, job)
    _logger.info("rolled back job %s: %d step(s) reversed", job.job_id, len(reversed_events))
    return job


class DestinationClaims:
    """Reserves destinations during one run, so no two units are planned for the same path.

    ``sort`` and ``reclassify`` both plan a whole batch before moving anything. Each asks this
    for every destination in turn: the first unit to claim a free path gets it, and a later unit
    headed for the same path (or for a path something already occupies) is told why it can't.
    ``file_batch`` still refuses to overwrite as the last line of defence, for a path taken
    between planning and moving.

    Args:
        library: The library being filed into; used to word the reasons relative to its root.
    """

    def __init__(self, library: Library) -> None:
        self._library = library
        self._claimed: set[Path] = set()

    def claim(self, destination: Path) -> str | None:
        """Reserve ``destination`` for a unit, unless it is already taken.

        Args:
            destination: Where a unit would be filed (see ``destination_for``).

        Returns:
            ``None`` if the path was free and is now reserved; otherwise the reason it can't be
            used, which names the path relative to the library. Nothing is reserved then.
        """

        problem = self.problem(destination)
        if problem is None:
            self._claimed.add(destination)
        return problem

    def problem(self, destination: Path) -> str | None:
        """Say why ``destination`` cannot be used, without reserving it.

        Args:
            destination: Where a unit would be filed (see ``destination_for``).

        Returns:
            ``None`` if the path is free, otherwise the reason it is not, naming the path relative to the library.
        """

        if destination.exists():
            return f"'{destination.name}' already exists in {self._library.relative(destination.parent)}"
        if destination in self._claimed:
            return f"another unit in this run is already going to {self._library.relative(destination)}"
        return None


def destination_for(library: Library, folders: tuple[str, ...], source_name: str) -> Path:
    """Work out where ``file_batch`` will put a unit, after the library's naming rules.

    Lets callers (such as ``microfiche.core.reclassify``) preview a move, or spot a clash, without filing.

    Args:
        library: The library being filed into.
        folders: The folder names the unit belongs under (``ClassificationResult.folders``): its group, and
            its category in a library that has them.
        source_name: The unit's current file or folder name.

    Returns:
        The path the unit would be filed at.
    """

    return library.target_dir(*folders) / apply_naming_rules(source_name, library.config.naming_rules.rules)


def load_job(state_dir: Path, job_id: str) -> Job:
    """Load ``<state_dir>/rollback/job_<job_id>.json``.

    Args:
        state_dir: The library's ``.microfiche`` folder.
        job_id: The id of the job to load.

    Returns:
        The saved job.

    Raises:
        JobNotFoundError: if the id is malformed or no such job file exists.
    """

    job_path = state_dir / _ROLLBACK_DIRNAME / f"job_{job_id}.json"
    if not _JOB_ID_RE.fullmatch(job_id) or not job_path.exists():
        raise JobNotFoundError(job_id, job_path)
    return Job.model_validate_json(job_path.read_text(encoding="utf-8"))


def latest_job(state_dir: Path) -> Job:
    """The newest job that has not been rolled back, so ``rollback --last`` needn't be given an id.

    Jobs are ordered by when they were created, not by file name, so two jobs made in the same second are
    still told apart.

    Args:
        state_dir: The library's ``.microfiche`` folder.

    Returns:
        The most recently created job whose ``rolled_back_at`` is unset.

    A job file that cannot be read (truncated, hand-edited, from another version) is skipped with a warning rather than
    stopping the command, so one damaged file does not make the healthy jobs unreachable.

    Raises:
        NoJobToRollBackError: if there is no readable job that is still applied, naming any files that could not be read.
    """

    applied: list[Job] = []
    unreadable: list[Path] = []
    for path in sorted((state_dir / _ROLLBACK_DIRNAME).glob("job_*.json")):
        try:
            job = Job.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:  # a pydantic ValidationError is a ValueError, and so is a bad encoding
            _logger.warning("skipped unreadable job file %s: %s", path.name, describe_error(err))
            unreadable.append(path)
            continue
        if job.rolled_back_at is None:
            applied.append(job)
    if not applied:
        raise NoJobToRollBackError(state_dir, unreadable)
    return max(applied, key=lambda job: job.created_at)


def save_job(state_dir: Path, job: Job) -> Path:
    """Write ``job`` to ``<state_dir>/rollback/job_<id>.json``, creating the folder if needed.

    Args:
        state_dir: The library's ``.microfiche`` folder.
        job: The job to save.

    Returns:
        The path the job was written to.
    """

    rollback_dir = state_dir / _ROLLBACK_DIRNAME
    rollback_dir.mkdir(parents=True, exist_ok=True)
    job_path = rollback_dir / f"job_{job.job_id}.json"
    job_path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return job_path


# endregion


# region Helpers


def _file_unit(
    unit: SortableUnit,
    classification: ClassificationResult,
    library: Library,
    job_id: str,
) -> tuple[AuditEvent, LedgerRecord]:
    """Move one resolved unit into the library.

    Args:
        unit: The unit to move.
        classification: Its classification, which must be resolved (see ``ClassificationResult.folders``).
        library: The library to file into.
        job_id: The id of the job this move belongs to.

    Returns:
        The move's audit event and ledger record.

    Raises:
        UnresolvedClassificationError: if the classification is unresolved.
    """

    folders = classification.folders
    if folders is None or classification.group.name is None:
        raise UnresolvedClassificationError(unit.source_path.name)

    content_hash = unit_hash(unit.source_path)  # before the move, while the content is still at the source
    destination = destination_for(library, folders, unit.source_path.name)
    safe_move(unit.source_path, destination)
    _logger.debug("moved %s -> %s", library.relative(unit.source_path), library.relative(destination))

    event = AuditEvent(original_path=unit.source_path, new_path=destination, action="move")
    record = LedgerRecord(
        event="filed",
        job_id=job_id,
        path=library.relative(destination),
        original_path=library.relative(unit.source_path),
        content_hash=content_hash,
        unit_type=unit.kind,
        group=classification.group.name,
        category=classification.category.name if classification.category else None,
        group_reason=classification.group.reason,
        category_reason=classification.category.reason if classification.category else None,
        confidence=classification.overall_confidence,
        classified_by=classification.classified_by,
    )
    return event, record


def _describe_move_failure(err: OSError) -> str:
    """Say why a move failed, in words a person can act on."""

    if isinstance(err, FileExistsError):
        return "something took its place at the destination while sorting"
    if isinstance(err, PermissionError):
        if getattr(err, "winerror", None) in _FILE_IN_USE_WINERRORS:
            return "it is open in another program; close it and sort again"
        return "permission denied"
    return describe_error(err)


def _remove_emptied_folders(library: Library, job: Job, units: list[SortableUnit]) -> None:
    """Remove each inbox folder the units came from that now holds no file, recording every removal.

    A folder is removed only if its whole tree is empty directories. The directories go deepest first
    with ``Path.rmdir``, which refuses a directory that has anything in it, so no file can be lost.
    A folder that cannot be removed (for example one another program has open) is left as it is.

    Args:
        library: The library being filed into.
        job: The job to record the removals in.
        units: The units that were filed.
    """

    for origin in sorted({unit.origin_folder for unit in units if unit.origin_folder is not None}):
        if not origin.is_dir() or _holds_anything(origin):
            continue
        directories = sorted((p for p in origin.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True)
        for directory in [*directories, origin]:
            try:
                directory.rmdir()
            except OSError:
                break
            _logger.debug("removed empty folder %s", library.relative(directory))
            event = AuditEvent(original_path=directory, action="remove_folder")
            job.moves.append(event)
            _append_audit_lines(library, job.job_id, [event])


def _holds_anything(folder: Path) -> bool:
    """Whether ``folder`` contains anything other than real sub-folders, which are themselves empty of anything else.

    A symbolic link or junction counts as something, and is never entered: what it points at is not this folder's
    to clear, and ``Path.rglob`` would walk straight through a junction.
    """

    return any(is_link(entry) or not entry.is_dir() or _holds_anything(entry) for entry in folder.iterdir())


def _places(library: Library, event: AuditEvent, relocations: dict[str, list[str]]) -> list[str]:
    """Where the ledger has had ``event``'s unit: as filed first, then each place it was moved to by hand."""

    filed_at = library.relative(event.new_path) if event.new_path is not None else ""
    return relocations.get(filed_at, [filed_at])


def _note_if_edited(filed_hash: str | None, content_hash: str, hops: list[str], edited: list[str] | None) -> None:
    """Warn, and tell ``edited`` if given, when a unit about to be moved back no longer holds what was filed."""

    if filed_hash is None or filed_hash == content_hash:
        return
    _logger.warning("%s was edited since it was filed; moved back as it is", hops[-1])
    if edited is not None:
        edited.append(hops[0])


def _unreachable(library: Library, job: Job, relocations: dict[str, list[str]]) -> list[AuditEvent]:
    """The moves of ``job`` whose unit is at neither its current place nor its original one, so cannot be reversed."""

    return [
        event
        for event in job.moves
        if event.action == "move"
        and event.new_path is not None
        and not (library.root / _places(library, event, relocations)[-1]).exists()
        and not event.original_path.exists()
    ]


def _append_audit_lines(library: Library, job_id: str, events: list[AuditEvent]) -> None:
    """Append one ``<timestamp> job=<id> <action> <from> -> <to>`` line per event to ``audit.log``."""

    if not events:
        return
    lines = [
        f"{event.timestamp.isoformat(timespec='seconds')} job={job_id} {event.action} "
        f"{library.relative(event.original_path)} -> "
        f"{library.relative(event.new_path) if event.new_path is not None else '-'}\n"
        for event in events
    ]
    library.state_dir.mkdir(parents=True, exist_ok=True)
    with (library.state_dir / AUDIT_LOG_FILENAME).open("a", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(lines))


def _new_job_id() -> str:
    """A sortable, unique, filename-safe id like ``20261004-153012-a1b2c3``."""

    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


# endregion
