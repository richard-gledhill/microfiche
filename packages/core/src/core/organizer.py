"""Ties scanning, classification, and filing together into the `sort` pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.ai.llm_classifier import LLMClassifier
from core.classifier import Classifier
from core.filer import file_batch
from core.library.library import Library
from core.models.audit_event import AuditEvent
from core.models.classification import ClassificationResult
from core.models.job import Job
from core.models.unit import SortableUnit
from core.scanner import scan_sorting_inbox


@dataclass
class SortReport:
    """Summary of one `sort` run."""

    filed: list[tuple[SortableUnit, ClassificationResult]] = field(default_factory=list)
    needs_review: list[tuple[SortableUnit, ClassificationResult]] = field(default_factory=list)
    audit_events: list[AuditEvent] = field(default_factory=list)
    job: Job | None = None


def run_sort(
    library: Library,
    *,
    keep_folders: bool = False,
    ai_classifier: LLMClassifier | None = None,
) -> SortReport:
    """Scan the library's inbox, classify each unit, and file everything confident enough to
    file (see ``config.classification.confidence_threshold``) as one job (see ``core.filer``).
    Anything below it is returned in ``needs_review`` instead of being moved. ``SortReport.job``
    is ``None`` if nothing was filed."""

    taxonomy = library.taxonomy()
    classifier = Classifier.from_config(library.config, ai_classifier)

    report = SortReport()
    for unit in scan_sorting_inbox(library, keep_folders=keep_folders):
        classification = classifier.classify_unit(unit, taxonomy)
        if classification.confident:
            report.filed.append((unit, classification))
        else:
            report.needs_review.append((unit, classification))

    report.job = file_batch(library, report.filed)
    if report.job is not None:
        report.audit_events.extend(report.job.moves)

    return report
