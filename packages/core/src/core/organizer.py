"""Ties scanning, classification, and filing together into the `sort` pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.ai.llm_classifier import LLMClassifier
from core.classifier import CONFIDENCE_THRESHOLD, Classifier
from core.config import MicroficheConfig
from core.filer import file_unit
from core.library.taxonomy import discover_taxonomy
from core.models.audit_event import AuditEvent
from core.models.classification import ClassificationResult
from core.models.unit import SortableUnit
from core.rules.rules_engine import RulesEngine
from core.scanner import scan_sorting_inbox


@dataclass
class SortReport:
    """Summary of one `sort` run."""

    filed: list[tuple[SortableUnit, ClassificationResult]] = field(default_factory=list)
    needs_review: list[tuple[SortableUnit, ClassificationResult]] = field(default_factory=list)
    audit_events: list[AuditEvent] = field(default_factory=list)


def run_sort(
    library_root: Path,
    config: MicroficheConfig,
    *,
    keep_folders: bool = False,
    ai_classifier: LLMClassifier | None = None,
) -> SortReport:
    """Scan the sorting inbox, classify each unit, and file everything at or above the confidence
    threshold. Anything below it is returned in ``needs_review`` instead of being moved."""

    taxonomy = discover_taxonomy(library_root, config.exclusions.exclude)
    rules_engine = RulesEngine(config.category_hints.categories, config.filing_rules.rules)
    classifier = Classifier(rules_engine, ai_classifier)

    report = SortReport()
    for unit in scan_sorting_inbox(library_root, keep_folders=keep_folders):
        classification = classifier.classify_unit(unit, taxonomy)
        if classification.overall_confidence >= CONFIDENCE_THRESHOLD:
            events = file_unit(unit, classification, library_root, naming_rules=config.naming_rules.rules)
            report.filed.append((unit, classification))
            report.audit_events.extend(events)
        else:
            report.needs_review.append((unit, classification))

    return report
