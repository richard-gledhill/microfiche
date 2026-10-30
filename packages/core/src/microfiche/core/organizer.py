"""Ties scanning, classification, and filing together into the `sort` pipeline."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from microfiche.core.ai.llm_classifier import LLMClassifier
from microfiche.core.classifier import Classifier, VerificationStats
from microfiche.core.duplicates import Duplicate, DuplicateIndex
from microfiche.core.filer import DestinationClaims, destination_for, file_batch
from microfiche.core.library.library import Library
from microfiche.core.library.library_sync import LibrarySync, sync_library_file
from microfiche.core.models.classification import ClassificationResult
from microfiche.core.models.job import Job
from microfiche.core.models.unit import SortableUnit
from microfiche.core.scanner import scan_sorting_inbox
from microfiche.core.utils.filesystem import is_link

_logger = logging.getLogger(__name__)

_KEPT_REASON_FILES = 3  # how many remaining files a "folder kept" reason names before saying "and N more"


@dataclass
class SortReport:
    """Summary of one `sort` run.

    Attributes:
        filed: Each unit that was filed, with its classification.
        needs_review: Each unit left in the inbox for review, with its classification.
        duplicates: Each inbox file left where it is because the library already has a copy of it (or
            another inbox file with the same content is being filed this run), with the reason.
        job: The rollback job for the run, or ``None`` if nothing was filed.
        skipped_links: Symbolic links and junctions in the inbox that were passed over, never followed.
        ai_unavailable: Why the AI fallback stopped being asked part-way through the run (a connection
            failure or a timeout), or ``None``. The rest of the run used the rules only.
        folders_removed: Inbox folders whose files were all filed and which were then removed (the job records
            them, so ``rollback`` recreates them).
        folders_kept: Inbox folders that files were taken from but which still hold something, each with why.
        into_empty_groups: How many of ``filed`` go straight into a group because it has no category folders.
        by_learned_hint: How many of ``filed`` were decided by a keyword hint microfiche learned.
        ai_verification: How many rules answers the AI was asked to check (``[ai] verify_below``), confirmed and overruled.
        dry_run: Whether this was a preview. Nothing was moved or recorded: ``filed`` is what would be filed,
            ``folders_removed`` the folders that would be removed once emptied, and ``job`` is ``None``.
        library_sync: What the run found out about the library file: folders it added an entry for, and entries
            with no folder. ``None`` for a preview, which writes nothing.
    """

    filed: list[tuple[SortableUnit, ClassificationResult]] = field(default_factory=list)
    needs_review: list[tuple[SortableUnit, ClassificationResult]] = field(default_factory=list)
    duplicates: list[Duplicate] = field(default_factory=list)
    job: Job | None = None
    skipped_links: list[Path] = field(default_factory=list)
    ai_unavailable: str | None = None
    folders_removed: list[Path] = field(default_factory=list)
    folders_kept: list[tuple[Path, str]] = field(default_factory=list)
    into_empty_groups: int = 0
    by_learned_hint: int = 0
    ai_verification: VerificationStats = field(default_factory=VerificationStats)
    dry_run: bool = False
    library_sync: LibrarySync | None = None


def run_sort(
    library: Library,
    *,
    keep_folders: bool | None = None,
    ai_classifier: LLMClassifier | None = None,
    dry_run: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> SortReport:
    """Scan the library's inbox, classify each unit, and file the confident ones as one job.

    A unit is filed if it is confident enough (see ``config.classification.confidence_threshold``);
    the job is recorded by ``microfiche.core.filer``. Anything below the threshold is returned in
    ``needs_review`` instead of being moved.

    Unless this is a dry run, the library file is first brought in step with the folders (see
    ``microfiche.core.library.library_sync``), under the caller's run lock.

    Each unit is classified, then checked in this order, and the first check it fails holds it in the
    inbox: is its content already in the library or being filed this run (``duplicates``), then is
    its destination name taken (``needs_review``).

    Args:
        library: The library whose inbox to sort.
        keep_folders: Whether to keep each inbox folder whole as one unit. If not, its documents are filed
            one by one and the folder is removed once it is empty. ``None`` (the default) uses the
            library's ``[sorting] keep_folders`` setting.
        ai_classifier: An optional AI fallback for stages the rules can't answer confidently.
        dry_run: Classify and run every check as usual, but move nothing and write nothing: no job, ledger
            record or audit line. The report says what a real run would do. The AI, if given, is still asked.
        progress: Told how far the classification has got, so a caller can show it. Called as
            ``progress(done, total)``: first ``progress(0, total)`` before any unit is classified, then with the
            running count as each unit finishes, ending on ``progress(total, total)``. Core knows nothing about
            how it is shown.

    Returns:
        The report of what was filed and what needs review. ``SortReport.job`` is ``None`` if
        nothing was filed.
    """

    report = SortReport(dry_run=dry_run)
    if not dry_run:
        report.library_sync = sync_library_file(library)  # before the classifier reads the library file
    taxonomy = library.taxonomy()
    classifier = Classifier.from_library(library, ai_classifier)

    claims = DestinationClaims(library)
    duplicates = DuplicateIndex(library)
    scan = scan_sorting_inbox(library, keep_folders=keep_folders)
    report.skipped_links = scan.skipped_links
    label = " (dry run)" if dry_run else ""
    total = len(scan.units)
    _logger.info("sort%s: %d unit(s) to classify", label, total)
    for done, unit in enumerate(scan.units):
        if progress is not None:
            progress(done, total)
        classification = classifier.classify_unit(unit, taxonomy)
        duplicate = duplicates.check(unit, classification)
        if duplicate is not None:
            _logger.debug("%s: held as a duplicate (%s)", unit.source_path.name, duplicate.reason)
            report.duplicates.append(duplicate)
            continue
        classification = _reserve_destination(unit, classification, library, claims, duplicates)
        if classification.confident:
            _logger.debug("%s: to be filed under %s", unit.source_path.name, " / ".join(classification.folders or ()))
            report.filed.append((unit, classification))
        else:
            _logger.debug(
                "%s: left for review (confidence %.2f)", unit.source_path.name, classification.overall_confidence
            )
            report.needs_review.append((unit, classification))
    if progress is not None:
        progress(total, total)

    if not dry_run:
        _file_confident_units(library, report)
    _report_inbox_folders(report)
    report.ai_verification = classifier.verification
    report.by_learned_hint = sum(1 for _, c in report.filed if c.by_learned_hint)
    report.into_empty_groups = sum(1 for _, c in report.filed if len(c.folders or ()) < taxonomy.depth)
    if ai_classifier is not None:
        report.ai_unavailable = ai_classifier.failure

    _logger.info(
        "sort%s finished: %d filed, %d for review, %d duplicate(s)",
        label,
        len(report.filed),
        len(report.needs_review),
        len(report.duplicates),
    )
    return report


def _file_confident_units(library: Library, report: SortReport) -> None:
    """File ``report.filed`` as one job; a unit that could not be moved goes to ``needs_review`` instead."""

    result = file_batch(library, report.filed)
    report.job = result.job
    if not result.failed:
        return

    why = {failure.unit.source_path: failure.reason for failure in result.failed}
    still_filed: list[tuple[SortableUnit, ClassificationResult]] = []
    for unit, classification in report.filed:
        if unit.source_path in why:
            held = classification.held(f"it could not be moved: {why[unit.source_path]}")
            report.needs_review.append((unit, held))
        else:
            still_filed.append((unit, classification))
    report.filed = still_filed


def _report_inbox_folders(report: SortReport) -> None:
    """Fill in which inbox folders were removed once emptied, and why each of the others stayed.

    After a real run the folders on disk say which were removed. In a preview nothing has moved, so a
    folder counts as removed if everything that would be filed from it is all it holds.
    """

    units = [unit for unit, _ in (*report.filed, *report.needs_review)] + [d.unit for d in report.duplicates]
    origins = sorted({unit.origin_folder for unit in units if unit.origin_folder is not None})
    held = {unit.source_path: "needs review" for unit, _ in report.needs_review}
    held.update({duplicate.unit.source_path: "duplicate" for duplicate in report.duplicates})
    would_move = {unit.source_path for unit, _ in report.filed} if report.dry_run else set()
    for origin in origins:
        remaining = sorted(
            path for path in origin.rglob("*") if (is_link(path) or not path.is_dir()) and path not in would_move
        )
        if not origin.exists() or (report.dry_run and not remaining):
            report.folders_removed.append(origin)
        else:
            report.folders_kept.append((origin, _why_folder_kept(origin, held, remaining)))


def _why_folder_kept(folder: Path, held: dict[Path, str], remaining: list[Path]) -> str:
    """Name what still holds an inbox folder open: files held back (and why), and files that are not documents."""

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

    folders = classification.folders
    if not classification.confident or folders is None:
        return classification

    destination = destination_for(library, folders, unit.source_path.name)
    taken = claims.claim(destination)
    if taken is None:
        duplicates.add(unit.source_path, destination)
        return classification
    return classification.held(taken)
