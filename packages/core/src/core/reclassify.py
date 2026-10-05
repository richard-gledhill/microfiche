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
from core.filer import destination_for, file_batch
from core.library.library import Library
from core.models.classification import ClassificationResult
from core.models.job import Job
from core.models.unit import SortableUnit
from core.parsers import is_supported, read_documents

ReclassifyAction = Literal["move", "keep", "review", "conflict"]


@dataclass
class ReclassifyProposal:
    """One filed document, where the classifier would put it now, and what applying would do.

    Attributes:
        unit: The document as a sortable unit (its ``source_path`` is where it is now).
        classification: What the classifier thinks of it now.
        action: ``"move"`` it to ``destination``; ``"keep"`` it (already under the right
            category folder); ``"review"`` it (unresolved or not confident enough, so never
            moved automatically); or ``"conflict"`` (``destination`` is already taken, by an
            existing file or by another proposal in the same run, so it is left alone).
        destination: Where it would be filed; ``None`` for ``"review"`` and ``"keep"``.
    """

    unit: SortableUnit
    classification: ClassificationResult
    action: ReclassifyAction
    destination: Path | None = None

    @property
    def current_path(self) -> Path:
        """Where the document is filed now."""

        return self.unit.source_path

    @property
    def proposed_group(self) -> str | None:
        """The group the classifier would file it under, or ``None`` if unresolved."""

        return self.classification.group.name

    @property
    def proposed_category(self) -> str | None:
        """The category the classifier would file it under, or ``None`` if unresolved."""

        return self.classification.category.name


def run_reclassify(library: Library, *, scope: Path | None = None) -> list[ReclassifyProposal]:
    """Classify already-filed documents and report where the classifier would file each now.

    Covers everything under ``scope``, or the whole library minus exclusions. Never moves
    anything. Pass the result to ``apply_reclassification`` to act on the proposals whose action
    is ``"move"``.

    Args:
        library: The library whose filed documents to re-classify.
        scope: A folder inside the library to limit the run to; the whole library if omitted.

    Returns:
        One proposal per supported filed document.

    Raises:
        ScopeOutsideLibraryError: if ``scope`` is given but isn't inside the library.
    """

    taxonomy = library.taxonomy()
    classifier = Classifier.from_config(library.config)

    claimed: set[Path] = set()
    proposals: list[ReclassifyProposal] = []
    for file_path in library.files(scope):
        if not is_supported(file_path):
            continue

        read = read_documents([file_path])
        unit = SortableUnit(source_path=file_path, kind="file", documents=read.documents, unreadable=read.unreadable)
        classification = classifier.classify_unit(unit, taxonomy)
        proposals.append(_plan(unit, classification, library, claimed))

    return proposals


def apply_reclassification(library: Library, proposals: list[ReclassifyProposal]) -> Job | None:
    """File every proposal whose action is ``"move"`` as one job (see ``core.filer.file_batch``).

    Args:
        library: The library the proposals were made for.
        proposals: The result of ``run_reclassify``.

    Returns:
        The saved job, or ``None`` if there was nothing to move.

    Raises:
        FileExistsError: if a destination was taken after the proposals were made. Moves already
            made are saved as a job and can be rolled back.
    """

    items = [(proposal.unit, proposal.classification) for proposal in proposals if proposal.action == "move"]
    return file_batch(library, items)


def _plan(
    unit: SortableUnit,
    classification: ClassificationResult,
    library: Library,
    claimed: set[Path],
) -> ReclassifyProposal:
    """Decide what to do with one classified document; ``claimed`` holds destinations already planned."""

    group, category = classification.group.name, classification.category.name
    if group is None or category is None or not classification.confident:
        return ReclassifyProposal(unit, classification, "review")

    destination = destination_for(library, group, category, unit.source_path.name)
    current = unit.source_path
    if destination.parent == current.parent or destination.parent in current.parents:
        return ReclassifyProposal(unit, classification, "keep")
    if destination.exists() or destination in claimed:
        return ReclassifyProposal(unit, classification, "conflict", destination)

    claimed.add(destination)
    return ReclassifyProposal(unit, classification, "move", destination)
