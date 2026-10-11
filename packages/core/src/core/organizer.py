"""Ties scanning, classification, and filing together into the `sort` pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.ai.llm_classifier import LLMClassifier
from core.classifier import Classifier
from core.duplicates import Duplicate, DuplicateIndex
from core.filer import DestinationClaims, destination_for, file_batch
from core.library.library import Library
from core.models.audit_event import AuditEvent
from core.models.classification import ClassificationResult
from core.models.job import Job
from core.models.unit import SortableUnit
from core.scanner import scan_sorting_inbox

_KEPT_REASON_FILES = 3  # how many remaining files a "folder kept" reason names before saying "and N more"


@dataclass
class SortReport:
    """Summary of one `sort` run.

    Attributes:
        filed: Each unit that was filed, with its classification.
        needs_review: Each unit left in the inbox for review, with its classification.
        duplicates: Each inbox file left where it is because the library already has a copy of it (or
            another inbox file with the same content is being filed this run), with the reason.
        audit_events: The move events recorded for the filed units.
        job: The rollback job for the run, or ``None`` if nothing was filed.
        folders_removed: Inbox folders whose files were all filed and which were then removed (the job records
            them, so ``rollback`` recreates them).
        folders_kept: Inbox folders that files were taken from but which still hold something, each with why.
    """

    filed: list[tuple[SortableUnit, ClassificationResult]] = field(default_factory=list)
    needs_review: list[tuple[SortableUnit, ClassificationResult]] = field(default_factory=list)
    duplicates: list[Duplicate] = field(default_factory=list)
    audit_events: list[AuditEvent] = field(default_factory=list)
    job: Job | None = None
    folders_removed: list[Path] = field(default_factory=list)
    folders_kept: list[tuple[Path, str]] = field(default_factory=list)


def run_sort(
    library: Library,
    *,
    keep_folders: bool | None = None,
    ai_classifier: LLMClassifier | None = None,
) -> SortReport:
    """Scan the library's inbox, classify each unit, and file the confident ones as one job.

    A unit is filed if it is confident enough (see ``config.classification.confidence_threshold``);
    the job is recorded by ``core.filer``. Anything below the threshold is returned in
    ``needs_review`` instead of being moved.

    Each unit is classified, then checked in this order, and the first check it fails holds it in the
    inbox: is its content already in the library or being filed this run (``duplicates``), then is
    its destination name taken (``needs_review``).

    Args:
        library: The library whose inbox to sort.
        keep_folders: Whether to keep each inbox folder whole as one unit. If not, its documents are filed
            one by one and the folder is removed once it is empty. ``None`` (the default) uses the
            library's ``[sorting] keep_folders`` setting.
        ai_classifier: An optional AI fallback for stages the rules can't answer confidently.

    Returns:
        The report of what was filed and what needs review. ``SortReport.job`` is ``None`` if
        nothing was filed.
    """

    taxonomy = library.taxonomy()
    classifier = Classifier.from_library(library, ai_classifier)

    claims = DestinationClaims(library)
    duplicates = DuplicateIndex(library)
    report = SortReport()
    for unit in scan_sorting_inbox(library, keep_folders=keep_folders):
        classification = classifier.classify_unit(unit, taxonomy)
        duplicate = duplicates.check(unit, classification)
        if duplicate is not None:
            report.duplicates.append(duplicate)
            continue
        classification = _reserve_destination(unit, classification, library, claims, duplicates)
        if classification.confident:
            report.filed.append((unit, classification))
        else:
            report.needs_review.append((unit, classification))

    report.job = file_batch(library, report.filed)
    if report.job is not None:
        report.audit_events.extend(report.job.moves)
    _report_inbox_folders(report)

    return report


def _report_inbox_folders(report: SortReport) -> None:
    """Fill in which inbox folders were removed once emptied, and why each of the others stayed."""

    units = [unit for unit, _ in (*report.filed, *report.needs_review)] + [d.unit for d in report.duplicates]
    origins = sorted({unit.origin_folder for unit in units if unit.origin_folder is not None})
    held = {unit.source_path: "needs review" for unit, _ in report.needs_review}
    held.update({duplicate.unit.source_path: "duplicate" for duplicate in report.duplicates})
    for origin in origins:
        if origin.exists():
            report.folders_kept.append((origin, _why_folder_kept(origin, held)))
        else:
            report.folders_removed.append(origin)


def _why_folder_kept(folder: Path, held: dict[Path, str]) -> str:
    """Name what still holds an inbox folder open: files held back (and why), and files that are not documents."""

    remaining = sorted(path for path in folder.rglob("*") if not path.is_dir())
    if not remaining:
        return "it could not be removed"
    shown = [
        f"{path.relative_to(folder).as_posix()} ({held.get(path, 'not sorted')})"
        for path in remaining[:_KEPT_REASON_FILES]
    ]
    more = len(remaining) - len(shown)
    return "it still holds " + ", ".join(shown) + (f" and {more} more" if more > 0 else "")


def _reserve_destination(
    unit: SortableUnit,
    classification: ClassificationResult,
    library: Library,
    claims: DestinationClaims,
    duplicates: DuplicateIndex,
) -> ClassificationResult:
    """Reserve a confident unit's destination, or leave it for review if the name is already taken.

    The destination is the one ``file_batch`` will use, after the naming rules. The group and
    category stay as classified, so ``review`` can show where it would have gone; only
    ``confident`` changes, and the category's reason gains the collision.

    A unit that gets its destination is also registered with ``duplicates``, so a later inbox file
    with the same content is held as a copy of it.
    """

    group, category = classification.group.name, classification.category.name
    if not classification.confident or group is None or category is None:
        return classification

    destination = destination_for(library, group, category, unit.source_path.name)
    taken = claims.claim(destination)
    if taken is None:
        duplicates.add(unit.source_path, destination)
        return classification
    held_category = classification.category.model_copy(
        update={"reason": f"{classification.category.reason}; but {taken}"}
    )
    return classification.model_copy(update={"confident": False, "category": held_category})
