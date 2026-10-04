"""Re-runs classification against documents already filed in the library, and can re-file them.

``run_reclassify`` is always a preview: it classifies each filed document and records what
``apply_reclassification`` *would* do about it. Applying goes through ``core.filer.file_batch``,
exactly like an initial ``sort``, so a reclassification is one job that is recorded in the
ledger and audit log and can be undone with ``rollback``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from core.classifier import Classifier
from core.config import MicroficheConfig
from core.extractor import extract
from core.filer import destination_for, file_batch
from core.library.taxonomy import discover_taxonomy
from core.models.classification import ClassificationResult
from core.models.job import Job
from core.models.unit import SortableUnit
from core.parsers import SUPPORTED_EXTENSIONS
from core.rules.rules_engine import RulesEngine
from core.utils.filesystem import is_excluded

ReclassifyAction = Literal["move", "keep", "review", "conflict"]


class ScopeOutsideLibraryError(ValueError):
    """Raised when asked to reclassify a folder that isn't inside the library."""

    def __init__(self, scope: Path, library_root: Path) -> None:
        self.scope = scope
        super().__init__(f"Scope '{scope}' is not inside the library '{library_root}'")


@dataclass
class ReclassifyProposal:
    """One filed document, where the classifier would put it now, and what applying would do.

    Attributes:
        unit: The document as a sortable unit (its ``source_path`` is where it is now).
        classification: What the classifier thinks of it now.
        action: ``"move"`` it to ``destination``; ``"keep"`` it (already under the right
            category folder); ``"review"`` it (unresolved or below the confidence threshold, so
            never moved automatically); or ``"conflict"`` (``destination`` is already taken, by
            an existing file or by another proposal in the same run, so it is left alone).
        destination: Where it would be filed; ``None`` for ``"review"`` and ``"keep"``.
    """

    unit: SortableUnit
    classification: ClassificationResult
    action: ReclassifyAction
    destination: Path | None = None

    @property
    def current_path(self) -> Path:
        return self.unit.source_path

    @property
    def proposed_group(self) -> str | None:
        return self.classification.group.name

    @property
    def proposed_category(self) -> str | None:
        return self.classification.category.name


def run_reclassify(
    library_root: Path, config: MicroficheConfig, *, scope: Path | None = None
) -> list[ReclassifyProposal]:
    """Classify already-filed documents under ``scope`` (or the whole library, minus exclusions)
    and report, for each, where the classifier would file it now.

    Never moves anything. Pass the result to ``apply_reclassification`` to act on the proposals
    whose action is ``"move"``.

    Raises:
        ScopeOutsideLibraryError: if ``scope`` is given but isn't inside ``library_root``.
    """

    taxonomy = discover_taxonomy(library_root, config.exclusions.exclude)
    classifier = Classifier(
        RulesEngine(config.category_hints.categories, config.filing_rules.rules),
        threshold=config.classification.confidence_threshold,
    )
    naming_rules = config.naming_rules.rules

    search_root = _search_root(library_root, scope)
    claimed: set[Path] = set()
    proposals: list[ReclassifyProposal] = []
    for file_path in sorted(search_root.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if is_excluded(file_path, config.exclusions.exclude):
            continue

        document = extract(file_path)
        unit = SortableUnit(source_path=file_path, kind="file", documents=[document])
        classification = classifier.classify_unit(unit, taxonomy)
        proposals.append(_plan(unit, classification, library_root, naming_rules, claimed))

    return proposals


def apply_reclassification(
    library_root: Path, config: MicroficheConfig, proposals: list[ReclassifyProposal]
) -> Job | None:
    """File every proposal whose action is ``"move"`` as one job (see ``core.filer.file_batch``).

    Args:
        library_root: The library's root folder.
        config: The library's configuration (for naming rules).
        proposals: The result of ``run_reclassify``.

    Returns:
        The saved job, or ``None`` if there was nothing to move.

    Raises:
        FileExistsError: if a destination was taken after the proposals were made. Moves already
            made are saved as a job and can be rolled back.
    """

    items = [(proposal.unit, proposal.classification) for proposal in proposals if proposal.action == "move"]
    return file_batch(library_root, items, naming_rules=config.naming_rules.rules)


def _search_root(library_root: Path, scope: Path | None) -> Path:
    """``scope`` re-expressed under ``library_root``'s own spelling of the path.

    Proposals compare file locations with ``library_root``-based destinations, so a relative or
    differently-spelled ``--folder`` must not leak through as-is.
    """

    if scope is None:
        return library_root
    try:
        return library_root / scope.resolve().relative_to(library_root.resolve())
    except ValueError as err:
        raise ScopeOutsideLibraryError(scope, library_root) from err


def _plan(
    unit: SortableUnit,
    classification: ClassificationResult,
    library_root: Path,
    naming_rules: dict[str, str],
    claimed: set[Path],
) -> ReclassifyProposal:
    """Decide what to do with one classified document; ``claimed`` holds destinations already planned."""

    group, category = classification.group.name, classification.category.name
    if group is None or category is None or not classification.confident:
        return ReclassifyProposal(unit, classification, "review")

    destination = destination_for(library_root, group, category, unit.source_path.name, naming_rules)
    current = unit.source_path
    if destination.parent == current.parent or destination.parent in current.parents:
        return ReclassifyProposal(unit, classification, "keep")
    if destination.exists() or destination in claimed:
        return ReclassifyProposal(unit, classification, "conflict", destination)

    claimed.add(destination)
    return ReclassifyProposal(unit, classification, "move", destination)
