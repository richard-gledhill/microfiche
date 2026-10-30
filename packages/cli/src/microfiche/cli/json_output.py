"""The JSON that ``--json`` prints: one versioned document per command, from models that are the public contract.

The core types (``SortReport``, ``ReclassifyProposal``, ...) hold paths and live objects and may change freely. These
models are what a script sees, so they are explicit, carry a ``version`` and have a committed JSON Schema each
(``schemas/``; ``make output-schemas`` regenerates them and a test fails if they go stale). They never
hold document text: only paths relative to the library, folder names, confidences and reasons.

Bump ``VERSION`` only for a change that breaks a reader: a field removed or renamed, or its meaning changed. Adding an
optional field does not.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Literal

from microfiche.core.classifier import VerificationStats
from microfiche.core.config import MicroficheConfig
from microfiche.core.filer import FailedFiling
from microfiche.core.library.library import Library
from microfiche.core.library.library_sync import LibrarySync
from microfiche.core.models.classification import ClassificationResult
from microfiche.core.models.job import Job
from microfiche.core.models.unit import SortableUnit
from microfiche.core.organizer import SortReport
from microfiche.core.reclassify import ReclassifyProposal
from microfiche.core.review import ReviewSession
from pydantic import BaseModel, Field

# region Constants and types

VERSION = 1
_AUDIT_LINE = re.compile(r"^(?P<timestamp>\S+) job=(?P<job_id>\S+) (?P<action>\S+) (?P<source>.*?) -> (?P<target>.*)$")


class _Output(BaseModel):
    """What every document has: the shape's version and the command that wrote it."""

    version: int = Field(default=VERSION, description="The shape's version. It changes only for a breaking change.")
    command: str


class Verification(BaseModel):
    """How many rules answers the AI was asked to check (``[ai] verify_below``) and what it said."""

    checked: int = 0
    confirmed: int = 0
    overruled: int = 0


class UnitEntry(BaseModel):
    """One inbox unit (or filed document) and where the classifier put it."""

    path: str = Field(description="Where the unit is, relative to the library, with forward slashes.")
    kind: Literal["file", "folder"]
    folders: list[str] | None = Field(
        description="The group, and category if the library has them, the unit was or would be filed under; null if unresolved."
    )
    confidence: float
    classified_by: str
    confident: bool
    reason: str = Field(description="Why the classifier chose that, or why it could not. Contains no document text.")
    destination: str | None = Field(default=None, description="Where the unit was filed (a filed unit of a real run).")


class DuplicateEntry(UnitEntry):
    """An inbox file left where it is because the library already holds a copy."""

    existing: str = Field(description="Where the copy is, relative to the library.")


class FolderKept(BaseModel):
    """An inbox folder that files were taken from but which still holds something."""

    path: str
    reason: str


class SyncEntry(BaseModel):
    """What a library file sync found."""

    created: bool
    added: list[str]
    missing: list[str]
    possible_renames: list[tuple[str, str]]
    name_warnings: list[str]
    write_error: str | None


class SortOutput(_Output):
    """The result of ``sort`` (and ``sort --dry-run``)."""

    command: Literal["sort"] = "sort"
    dry_run: bool
    filed: list[UnitEntry]
    needs_review: list[UnitEntry]
    duplicates: list[DuplicateEntry]
    skipped_links: list[str]
    job_id: str | None = Field(
        description="The job that filed them, for `rollback`; null for a preview or nothing filed."
    )
    ai_unavailable: str | None
    ai_verification: Verification
    filed_by_learned_hint: int
    filed_into_empty_groups: int
    folders_removed: list[str]
    folders_kept: list[FolderKept]
    library_sync: SyncEntry | None


class ProposalEntry(BaseModel):
    """What ``reclassify`` would do with one filed document or bundle."""

    path: str
    action: Literal["move", "keep", "review", "conflict"]
    folders: list[str] | None
    confidence: float
    reason: str
    destination: str | None


class FailureEntry(BaseModel):
    """A unit that could not be moved, and why."""

    path: str
    reason: str


class ReclassifyOutput(_Output):
    """The result of ``reclassify`` (a preview unless ``--apply``)."""

    command: Literal["reclassify"] = "reclassify"
    dry_run: bool
    proposals: list[ProposalEntry]
    job_id: str | None
    failed: list[FailureEntry]
    items_below_depth: int
    ai_unavailable: str | None
    ai_verification: Verification


class RollbackOutput(_Output):
    """The result of ``rollback``."""

    command: Literal["rollback"] = "rollback"
    job_id: str
    moves_reverted: int
    folders_recreated: int


class AuditEntry(BaseModel):
    """One line of the audit log."""

    timestamp: str
    job_id: str
    action: str
    source: str
    destination: str | None


class AuditOutput(_Output):
    """The audit log, parsed."""

    command: Literal["audit"] = "audit"
    entries: list[AuditEntry]
    unparsed: list[str] = Field(description="Lines that did not match the audit format, as written.")


class ConfigOutput(_Output):
    """``config``: the settings, or with ``--sync`` what the sync did."""

    command: Literal["config"] = "config"
    config: dict[str, Any] | None = Field(description="Every setting by section; null with --sync.")
    sync: SyncEntry | None = Field(description="What --sync did; null without it.")


class ReviewQueueOutput(_Output):
    """``review --list``: what `review` would ask about, without asking."""

    command: Literal["review"] = "review"
    items: list[UnitEntry]
    duplicates: list[DuplicateEntry]
    waiting: int = Field(description="Units confident enough for `sort` to file, which are not in the queue.")
    ai_unavailable: str | None


class ErrorOutput(_Output):
    """What stdout holds when a command stops before it can produce its result."""

    command: str = "error"
    error: str


OUTPUTS: dict[str, type[_Output]] = {
    "sort": SortOutput,
    "reclassify": ReclassifyOutput,
    "rollback": RollbackOutput,
    "audit": AuditOutput,
    "config": ConfigOutput,
    "review": ReviewQueueOutput,
    "error": ErrorOutput,
}

# endregion


# region Public API


def sort_output(report: SortReport, library: Library) -> SortOutput:
    """The JSON for a ``sort`` run."""

    destinations = _destinations(report.job, library)
    sync = report.library_sync
    return SortOutput(
        dry_run=report.dry_run,
        filed=[_unit(u, c, library, destinations.get(library.relative(u.source_path))) for u, c in report.filed],
        needs_review=[_unit(u, c, library) for u, c in report.needs_review],
        duplicates=[_duplicate(d.unit, d.classification, library, d.existing, d.reason) for d in report.duplicates],
        skipped_links=[library.relative(p) for p in report.skipped_links],
        job_id=report.job.job_id if report.job else None,
        ai_unavailable=report.ai_unavailable,
        ai_verification=_verification(report.ai_verification),
        filed_by_learned_hint=report.by_learned_hint,
        filed_into_empty_groups=report.into_empty_groups,
        folders_removed=[library.relative(p) for p in report.folders_removed],
        folders_kept=[FolderKept(path=library.relative(p), reason=why) for p, why in report.folders_kept],
        library_sync=_sync(sync) if sync is not None else None,
    )


def reclassify_output(
    proposals: Sequence[ReclassifyProposal],
    library: Library,
    *,
    dry_run: bool,
    job: Job | None,
    failed: Iterable[FailedFiling],
    below_depth: int,
    ai_unavailable: str | None,
) -> ReclassifyOutput:
    """The JSON for a ``reclassify`` run."""

    confirmed = sum(p.classification.confirmed_by_ai for p in proposals)
    overruled = sum(p.classification.ai_overruled for p in proposals)
    return ReclassifyOutput(
        dry_run=dry_run,
        proposals=[
            ProposalEntry(
                path=library.relative(p.current_path),
                action=p.action,
                folders=list(p.classification.folders) if p.classification.folders else None,
                confidence=p.classification.overall_confidence,
                reason=p.classification.reason,
                destination=library.relative(p.destination) if p.destination else None,
            )
            for p in proposals
        ],
        job_id=job.job_id if job else None,
        failed=[FailureEntry(path=library.relative(f.unit.source_path), reason=f.reason) for f in failed],
        items_below_depth=below_depth,
        ai_unavailable=ai_unavailable,
        ai_verification=Verification(checked=confirmed + overruled, confirmed=confirmed, overruled=overruled),
    )


def rollback_output(job: Job) -> RollbackOutput:
    """The JSON for a ``rollback``."""

    return RollbackOutput(
        job_id=job.job_id,
        moves_reverted=sum(1 for event in job.moves if event.action == "move"),
        folders_recreated=sum(1 for event in job.moves if event.action == "remove_folder"),
    )


def audit_output(text: str) -> AuditOutput:
    """The JSON for ``audit``: each line of the audit log parsed, with any line that does not parse kept as written."""

    entries: list[AuditEntry] = []
    unparsed: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = _AUDIT_LINE.match(line)
        if match is None:
            unparsed.append(line)
            continue
        target = match["target"]
        entries.append(
            AuditEntry(
                timestamp=match["timestamp"],
                job_id=match["job_id"],
                action=match["action"],
                source=match["source"],
                destination=None if target == "-" else target,
            )
        )
    return AuditOutput(entries=entries, unparsed=unparsed)


def config_output(config: MicroficheConfig | None, sync: LibrarySync | None) -> ConfigOutput:
    """The JSON for ``config``: the settings, or what ``--sync`` did."""

    return ConfigOutput(
        config=config.model_dump(mode="json") if config is not None else None,
        sync=_sync(sync) if sync is not None else None,
    )


def review_queue_output(session: ReviewSession, library: Library) -> ReviewQueueOutput:
    """The JSON for ``review --list``."""

    return ReviewQueueOutput(
        items=[_unit(item.unit, item.classification, library) for item in session.items],
        duplicates=[_duplicate(d.unit, d.classification, library, d.existing, d.reason) for d in session.duplicates],
        waiting=session.waiting,
        ai_unavailable=session.ai_unavailable,
    )


def output_schemas() -> dict[str, dict[str, Any]]:
    """The JSON Schema of each output, by command name, as committed in ``schemas/``."""

    schemas: dict[str, dict[str, Any]] = {}
    for name, model in OUTPUTS.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["title"] = f"microfiche {name} --json"
        schemas[name] = schema
    return schemas


def write_output_schemas(directory: Path) -> None:
    """Write each schema to ``directory`` as ``<command>.schema.json``."""

    directory.mkdir(parents=True, exist_ok=True)
    for name, schema in output_schemas().items():
        (directory / f"{name}.schema.json").write_text(
            json.dumps(schema, indent=2) + "\n", encoding="utf-8", newline="\n"
        )


# endregion


# region Helpers


def _unit(
    unit: SortableUnit, classification: ClassificationResult, library: Library, destination: str | None = None
) -> UnitEntry:
    return UnitEntry(
        path=library.relative(unit.source_path),
        kind=unit.kind,
        folders=list(classification.folders) if classification.folders else None,
        confidence=classification.overall_confidence,
        classified_by=classification.classified_by,
        confident=classification.confident,
        reason=classification.reason,
        destination=destination,
    )


def _duplicate(
    unit: SortableUnit, classification: ClassificationResult, library: Library, existing: Path, reason: str
) -> DuplicateEntry:
    entry = _unit(unit, classification, library)
    return DuplicateEntry(**entry.model_dump(exclude={"reason"}), reason=reason, existing=library.relative(existing))


def _destinations(job: Job | None, library: Library) -> dict[str, str]:
    """Where each moved unit went, by where it came from, both relative to the library."""

    if job is None:
        return {}
    return {
        library.relative(event.original_path): library.relative(event.new_path)
        for event in job.moves
        if event.action == "move" and event.new_path is not None
    }


def _verification(stats: VerificationStats) -> Verification:
    return Verification(checked=stats.checked, confirmed=stats.confirmed, overruled=stats.overruled)


def _sync(sync: LibrarySync) -> SyncEntry:
    return SyncEntry(
        created=sync.created,
        added=sync.added,
        missing=sync.missing,
        possible_renames=sync.possible_renames,
        name_warnings=sync.name_warnings,
        write_error=sync.write_error,
    )


# endregion
