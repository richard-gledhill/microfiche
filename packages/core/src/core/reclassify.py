"""Re-runs classification against documents already filed in the library, and can re-file them.

``run_reclassify`` is always a preview: it classifies each filed document and records what
``apply_reclassification`` *would* do about it. Applying goes through ``core.filer.file_batch``,
exactly like an initial ``sort``, so a reclassification is one job that is recorded in the
ledger and audit log and can be undone with ``rollback``.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from core.classifier import Classifier
from core.filer import DestinationClaims, FilingResult, destination_for, file_batch
from core.library.library import Library
from core.models.classification import ClassificationResult
from core.models.unit import SortableUnit
from core.parsers import is_supported, read_documents

ReclassifyAction = Literal["move", "keep", "review", "conflict"]

_logger = logging.getLogger(__name__)


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


def run_reclassify(
    library: Library,
    *,
    scope: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> list[ReclassifyProposal]:
    """Classify already-filed documents and report where the classifier would file each now.

    Covers everything under ``scope``, or the whole library minus exclusions. Never moves
    anything. Pass the result to ``apply_reclassification`` to act on the proposals whose action
    is ``"move"``.

    Args:
        library: The library whose filed documents to re-classify.
        scope: A folder inside the library to limit the run to; the whole library if omitted.
        progress: Told how far the run has got, as ``progress(done, total)``: first ``progress(0, total)``, then
            the running count as each document finishes, ending on ``progress(total, total)``.

    Returns:
        One proposal per supported filed document.

    Raises:
        ScopeOutsideLibraryError: if ``scope`` is given but isn't inside the library.
    """

    taxonomy = library.taxonomy()
    classifier = Classifier.from_library(library)

    claims = DestinationClaims(library)
    proposals: list[ReclassifyProposal] = []
    files = [path for path in library.files(scope) if is_supported(path)]
    total = len(files)
    for done, file_path in enumerate(files):
        if progress is not None:
            progress(done, total)
        read = read_documents([file_path], max_bytes=library.config.parsing.max_file_bytes)
        unit = SortableUnit(source_path=file_path, kind="file", documents=read.documents, unreadable=read.unreadable)
        classification = classifier.classify_unit(unit, taxonomy)
        proposal = _plan(unit, classification, library, claims)
        _logger.debug("%s: %s", library.relative(file_path), proposal.action)
        proposals.append(proposal)
    if progress is not None:
        progress(total, total)

    counts = Counter(proposal.action for proposal in proposals)
    _logger.info(
        "reclassify: checked %d document(s): %d move, %d keep, %d review, %d conflict",
        len(proposals),
        counts["move"],
        counts["keep"],
        counts["review"],
        counts["conflict"],
    )
    return proposals


def apply_reclassification(library: Library, proposals: list[ReclassifyProposal]) -> FilingResult:
    """File every proposal whose action is ``"move"`` as one job (see ``core.filer.file_batch``).

    A document that cannot be moved (open in another program, say, or a destination taken after the
    proposals were made) stays where it is and is listed in the result; the others are still moved.

    Args:
        library: The library the proposals were made for.
        proposals: The result of ``run_reclassify``.

    Returns:
        The saved job (``None`` if nothing was moved) and the documents that could not be moved.
    """

    items = [(proposal.unit, proposal.classification) for proposal in proposals if proposal.action == "move"]
    return file_batch(library, items)


def _plan(
    unit: SortableUnit,
    classification: ClassificationResult,
    library: Library,
    claims: DestinationClaims,
) -> ReclassifyProposal:
    """Decide what to do with one classified document; ``claims`` holds destinations already planned."""

    group, category = classification.group.name, classification.category.name
    if group is None or category is None or not classification.confident:
        return ReclassifyProposal(unit, classification, "review")

    destination = destination_for(library, group, category, unit.source_path.name)
    current = unit.source_path
    if library.filed_under(current, group, category):
        return ReclassifyProposal(unit, classification, "keep")
    if claims.claim(destination) is not None:
        return ReclassifyProposal(unit, classification, "conflict", destination)

    return ReclassifyProposal(unit, classification, "move", destination)
