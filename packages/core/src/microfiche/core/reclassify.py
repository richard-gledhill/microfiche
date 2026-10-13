"""Re-runs classification against documents already filed in the library, and can re-file them.

``run_reclassify`` is always a preview: it classifies each filed document and records what
``apply_reclassification`` *would* do about it. Applying goes through ``microfiche.core.filer.file_batch``,
exactly like an initial ``sort``, so a reclassification is one job that is recorded in the
ledger and audit log and can be undone with ``rollback``.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from microfiche.core.classifier import Classifier
from microfiche.core.filer import DestinationClaims, FilingResult, destination_for, file_batch
from microfiche.core.ledger import Ledger
from microfiche.core.library.library import Library
from microfiche.core.models.classification import ClassificationResult
from microfiche.core.models.unit import SortableUnit
from microfiche.core.parsers import is_supported, read_documents

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

        return self.classification.category.name if self.classification.category else None


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

    A folder that microfiche filed whole (``keep_folders``, recorded in the ledger) is one unit, classified by the
    dominant pair across its documents and proposed as a whole, so a filed bundle is never split. Any other folder
    below a category is just a place files sit: its files are classified one by one. To leave such a folder alone,
    list it under ``[exclusions]``.

    Args:
        library: The library whose filed documents to re-classify.
        scope: A folder inside the library to limit the run to; the whole library if omitted.
        progress: Told how far the run has got, as ``progress(done, total)``: first ``progress(0, total)``, then
            the running count as each document finishes, ending on ``progress(total, total)``.

    Returns:
        One proposal per supported filed document, or per filed bundle.

    Raises:
        ScopeOutsideLibraryError: if ``scope`` is given but isn't inside the library.
        LedgerCorruptError: if the ledger can't be read, so the filed bundles are not known.
    """

    taxonomy = library.taxonomy()
    classifier = Classifier.from_library(library)

    claims = DestinationClaims(library)
    proposals: list[ReclassifyProposal] = []
    items = _filed_items(library, scope)
    total = len(items)
    max_bytes = library.config.parsing.max_file_bytes
    for done, item in enumerate(items):
        if progress is not None:
            progress(done, total)
        read = read_documents(item.files, max_bytes=max_bytes)
        unit = SortableUnit(
            source_path=item.source, kind=item.kind, documents=read.documents, unreadable=read.unreadable
        )
        classification = classifier.classify_unit(unit, taxonomy)
        proposal = _plan(unit, classification, library, claims)
        _logger.debug("%s: %s", library.relative(unit.source_path), proposal.action)
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
    """File every proposal whose action is ``"move"`` as one job (see ``microfiche.core.filer.file_batch``).

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


def items_below_depth(library: Library) -> int:
    """How many filed items sit in folders below the library's depth.

    The ledger records where every item was filed, so this needs no scan of the library. After the depth is
    reduced (say from 2 to 1) the folders that were categories are plain folders, and the items filed in them
    are counted here; they are left where they are. A bundle counts once.

    Args:
        library: The library to check.

    Returns:
        The number of filed items deeper than ``[library_structure] depth`` allows (0 if none, or none filed).

    Raises:
        LedgerCorruptError: if the ledger can't be read.
    """

    depth = library.config.library_structure.depth
    # An item is filed inside its target folder: one name deeper than the number of levels. One that has since been
    # moved or deleted by hand is not there to count.
    return sum(
        1
        for record in Ledger(library.state_dir).current()
        if len(PurePosixPath(record.path).parts) > depth + 1 and (library.root / record.path).exists()
    )


@dataclass(frozen=True)
class _Filed:
    """Something to classify: one file, or a filed bundle with the supported files inside it."""

    source: Path
    kind: Literal["file", "folder"]
    files: list[Path]


def _filed_items(library: Library, scope: Path | None) -> list[_Filed]:
    """What to classify under ``scope``: each filed bundle as one item, every other supported file by itself.

    Nothing is read here, so the caller can report progress while the documents are parsed.
    """

    bundles = {library.root / path for path in Ledger(library.state_dir).folder_units()}
    items: list[_Filed] = []
    seen_bundles: set[Path] = set()
    for file_path in library.files(scope):
        if not is_supported(file_path):
            continue
        bundle = None
        for parent in file_path.parents:  # nearest first, so the last one found is the outermost
            if parent in bundles:
                bundle = parent
        if bundle is None:
            items.append(_Filed(file_path, "file", [file_path]))
        elif bundle not in seen_bundles:
            seen_bundles.add(bundle)
            # Every document in the bundle votes, even if ``scope`` covers only part of it: it is never split.
            items.append(_Filed(bundle, "folder", [path for path in library.files(bundle) if is_supported(path)]))
    return items


def _plan(
    unit: SortableUnit,
    classification: ClassificationResult,
    library: Library,
    claims: DestinationClaims,
) -> ReclassifyProposal:
    """Decide what to do with one classified document; ``claims`` holds destinations already planned."""

    folders = classification.folders
    if folders is None or not classification.confident:
        return ReclassifyProposal(unit, classification, "review")

    destination = destination_for(library, folders, unit.source_path.name)
    current = unit.source_path
    if library.filed_under(current, *folders):
        return ReclassifyProposal(unit, classification, "keep")
    if claims.claim(destination) is not None:
        return ReclassifyProposal(unit, classification, "conflict", destination)

    return ReclassifyProposal(unit, classification, "move", destination)
