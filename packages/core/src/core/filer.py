"""Files classified units into the library, records every move, and can undo a whole run.

One run of filing is a *job*. For each unit it moves, ``file_batch`` writes to three places under
the library's ``.microfiche/`` folder:

- ``rollback/job_<id>.json`` - the moves, so ``rollback_job`` can reverse them;
- ``ledger.jsonl`` - what each unit is, where it went, and why (see ``core.ledger``);
- ``audit.log`` - one human-readable line per move, shown by ``microfiche audit``.

Nothing is ever deleted: rollback moves units back, and the ledger and audit log only grow.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from core.ledger import Ledger
from core.library.library import Library
from core.library.naming import apply_naming_rules
from core.models.audit_event import AuditEvent
from core.models.classification import ClassificationResult
from core.models.job import Job
from core.models.ledger import LedgerRecord
from core.models.unit import SortableUnit
from core.utils.filesystem import ensure_dir, safe_move
from core.utils.hashing import unit_hash

AUDIT_LOG_FILENAME = "audit.log"
_ROLLBACK_DIRNAME = "rollback"
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class UnresolvedClassificationError(ValueError):
    """Raised when asked to file a unit whose group or category is unresolved.

    Callers must route unresolved classifications to the review queue instead of filing them.
    """

    def __init__(self, unit_name: str) -> None:
        self.unit_name = unit_name
        super().__init__(f"Cannot file '{unit_name}': its group or category is unresolved")


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


class JobMoveMissingError(FileNotFoundError):
    """Raised when a move can't be reversed because the file is at neither its old nor new location."""

    def __init__(self, event: AuditEvent) -> None:
        self.event = event
        super().__init__(f"Cannot roll back: '{event.new_path}' is gone and '{event.original_path}' does not exist")


def file_batch(library: Library, items: list[tuple[SortableUnit, ClassificationResult]]) -> Job | None:
    """Move each unit into its classified (group, category) folder and record the run as one job.

    The whole batch is checked for unresolved classifications before anything moves. If a move
    then fails part-way (for example because the destination already exists), the moves already
    made are still saved as the job - so they can be rolled back - and the error is re-raised.

    Each unit's name is rewritten by the library's naming rules as it is filed.

    Args:
        library: The library to file into.
        items: Pairs of a unit and its (resolved) classification.

    Returns:
        The saved ``Job``, or ``None`` if ``items`` is empty (nothing is written in that case).

    Raises:
        UnresolvedClassificationError: if any classification has no group or category.
        FileExistsError: if a destination already exists; nothing is ever overwritten.
    """

    if not items:
        return None
    for unit, classification in items:
        if classification.group.name is None or classification.category.name is None:
            raise UnresolvedClassificationError(unit.source_path.name)

    state_dir = library.state_dir
    ledger = Ledger(state_dir)
    job = Job(job_id=_new_job_id())
    try:
        for unit, classification in items:
            event, record = _file_unit(unit, classification, library, job.job_id)
            job.moves.append(event)
            ledger.append([record])
            _append_audit_lines(library, job.job_id, [event])
    finally:
        if job.moves:
            save_job(state_dir, job)
    return job


def rollback_job(library: Library, job_id: str) -> Job:
    """Reverse every move of a job, newest first, and mark the job as rolled back.

    Safe to retry: if an earlier attempt stopped part-way, moves that were already reversed are
    recognised (the unit is back at its original location) and skipped.

    Args:
        library: The library the job was run on.
        job_id: The id printed by ``sort`` (the ``job_<id>.json`` file name without its decoration).

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

    reversed_events: list[AuditEvent] = []
    records: list[LedgerRecord] = []
    try:
        for event in reversed(job.moves):
            if event.action != "move" or event.new_path is None:
                continue
            if not event.new_path.exists():
                if event.original_path.exists():
                    continue  # already put back by an earlier, interrupted rollback
                raise JobMoveMissingError(event)
            content_hash = unit_hash(event.new_path)
            unit_type: Literal["file", "folder"] = "folder" if event.new_path.is_dir() else "file"
            safe_move(event.new_path, event.original_path)
            reversed_events.append(
                AuditEvent(original_path=event.new_path, new_path=event.original_path, action="rollback")
            )
            records.append(
                LedgerRecord(
                    event="rolled_back",
                    job_id=job.job_id,
                    path=library.relative(event.new_path),
                    original_path=library.relative(event.original_path),
                    content_hash=content_hash,
                    unit_type=unit_type,
                )
            )
    finally:
        Ledger(state_dir).append(records)
        _append_audit_lines(library, job.job_id, reversed_events)

    job.rolled_back_at = datetime.now()
    save_job(state_dir, job)
    return job


def destination_for(library: Library, group: str, category: str, source_name: str) -> Path:
    """Where ``file_batch`` will put a unit called ``source_name`` classified as ``group``/``category``,
    after the library's naming rules.

    Lets callers (such as ``core.reclassify``) preview a move, or spot a clash, without filing.
    """

    return library.target_dir(group, category) / apply_naming_rules(source_name, library.config.naming_rules.rules)


def load_job(state_dir: Path, job_id: str) -> Job:
    """Load ``<state_dir>/rollback/job_<job_id>.json``.

    Raises:
        JobNotFoundError: if the id is malformed or no such job file exists.
    """

    job_path = state_dir / _ROLLBACK_DIRNAME / f"job_{job_id}.json"
    if not _JOB_ID_RE.fullmatch(job_id) or not job_path.exists():
        raise JobNotFoundError(job_id, job_path)
    return Job.model_validate_json(job_path.read_text(encoding="utf-8"))


def save_job(state_dir: Path, job: Job) -> Path:
    """Write ``job`` to ``<state_dir>/rollback/job_<id>.json`` (creating the folder) and return the path."""

    rollback_dir = state_dir / _ROLLBACK_DIRNAME
    rollback_dir.mkdir(parents=True, exist_ok=True)
    job_path = rollback_dir / f"job_{job.job_id}.json"
    job_path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return job_path


def _file_unit(
    unit: SortableUnit,
    classification: ClassificationResult,
    library: Library,
    job_id: str,
) -> tuple[AuditEvent, LedgerRecord]:
    """Move one resolved unit into the library; return its audit event and ledger record."""

    group, category = classification.group.name, classification.category.name
    if group is None or category is None:
        raise UnresolvedClassificationError(unit.source_path.name)

    content_hash = unit_hash(unit.source_path)  # before the move, while the content is still at the source
    destination = destination_for(library, group, category, unit.source_path.name)
    ensure_dir(destination.parent)
    safe_move(unit.source_path, destination)

    event = AuditEvent(original_path=unit.source_path, new_path=destination, action="move")
    record = LedgerRecord(
        event="filed",
        job_id=job_id,
        path=library.relative(destination),
        original_path=library.relative(unit.source_path),
        content_hash=content_hash,
        unit_type=unit.kind,
        group=group,
        category=category,
        group_reason=classification.group.reason,
        category_reason=classification.category.reason,
        confidence=classification.overall_confidence,
        classified_by=classification.classified_by,
    )
    return event, record


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
