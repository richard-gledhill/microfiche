"""Re-runs classification against documents already filed in the library, for drift detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.classifier import Classifier
from core.config import MicroficheConfig
from core.extractor import extract
from core.library.taxonomy import discover_taxonomy
from core.models.classification import ClassificationResult
from core.models.unit import SortableUnit
from core.parsers import SUPPORTED_EXTENSIONS
from core.rules.rules_engine import RulesEngine
from core.utils.filesystem import is_excluded


@dataclass
class ResortProposal:
    """One proposed re-filing: where a document currently is vs. where the classifier would put it now."""

    current_path: Path
    proposed_group: str | None
    proposed_category: str | None
    classification: ClassificationResult


def run_resort(library_root: Path, config: MicroficheConfig, *, scope: Path | None = None) -> list[ResortProposal]:
    """Dry-run only: classify already-filed documents under ``scope`` (or the whole library, minus
    exclusions) and report where the classifier would file them now.

    Never moves anything - the caller (the CLI) is responsible for presenting this and, if the
    user confirms with `--apply`, filing the proposals through ``core.filer.file_unit`` exactly
    like an initial sort.
    """

    taxonomy = discover_taxonomy(library_root, config.exclusions.exclude)
    classifier = Classifier(RulesEngine(config.category_hints.categories, config.filing_rules.rules))

    search_root = scope or library_root
    proposals: list[ResortProposal] = []
    for file_path in sorted(search_root.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if is_excluded(file_path, config.exclusions.exclude):
            continue

        document = extract(file_path)
        unit = SortableUnit(source_path=file_path, kind="file", documents=[document])
        classification = classifier.classify_unit(unit, taxonomy)
        proposals.append(
            ResortProposal(
                current_path=file_path,
                proposed_group=classification.group.name,
                proposed_category=classification.category.name,
                classification=classification,
            )
        )

    return proposals
