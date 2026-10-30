"""Simulates learning from review choices on the calibration corpus, with the documents of each category split.

For every category with more than ``min_decisions`` documents, the first ``min_decisions`` stay in the library and are
recorded in the ledger as filed by a person; the rest are held out. Hints are learned from the library as it then stands,
and each held-out document is classified with and without them. This measures what learning does to documents it has not
seen, which is what a user would get. The corpus is small (at most six documents in a category), so read the result as a
sanity check on the guardrails, not as a rate: docs/development/testing/calibration.md says so too.

Run: ``uv run python tests/calibration/learning_sim.py``.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from harness import CORPUS_ROOT, UNFILED
from microfiche.core.classifier import Classifier
from microfiche.core.learning import learn_hints
from microfiche.core.ledger import Ledger
from microfiche.core.library.library import Library
from microfiche.core.models.ledger import LedgerRecord
from microfiche.core.parsers import read_documents

SWEEP = ((2, 2), (3, 3), (5, 3), (3, 5))  # (min_decisions, max_hints_per_run)


@dataclass
class SimResult:
    """What learning did to the held-out documents of one run of the simulation."""

    min_decisions: int
    max_hints: int
    categories: int = 0
    hints: int = 0
    held_out: int = 0
    changed: int = 0
    now_right: int = 0
    now_wrong: int = 0
    was_wrong: int = 0


def simulate(min_decisions: int, max_hints: int, corpus_root: Path = CORPUS_ROOT) -> SimResult:
    """Learn from the first ``min_decisions`` documents of each category and test on the rest."""

    result = SimResult(min_decisions, max_hints)
    for source in sorted(p for p in corpus_root.iterdir() if p.is_dir()):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch) / source.name
            shutil.copytree(source, root)
            held = _split(root, min_decisions)
            if not held:
                continue
            _enable(root, min_decisions, max_hints)
            before = _classify(root, held)
            library = Library(root)
            learned = learn_hints(library, {(g, c) for g, c, _ in held}, "sim")
            result.hints += len(learned)
            result.categories += len({(h.group, h.category) for h in learned})
            after = _classify(root, held)
            for (group, category, _name), was, now in zip(held, before, after, strict=True):
                result.held_out += 1
                truth = (group, category)
                if was != now:
                    result.changed += 1
                result.was_wrong += was is not None and was != truth
                if now is not None and now != truth and was != now:
                    result.now_wrong += 1
                if now == truth and was != truth:
                    result.now_right += 1
    return result


def report() -> str:
    """The sweep as a table."""

    lines = ["min  cap  hints  held-out  changed  newly right  newly wrong"]
    for min_decisions, cap in SWEEP:
        r = simulate(min_decisions, cap)
        lines.append(
            f"{r.min_decisions:>3}  {r.max_hints:>3}  {r.hints:>5}  {r.held_out:>8}  {r.changed:>7}  "
            f"{r.now_right:>11}  {r.now_wrong:>11}"
        )
    return "\n".join(lines)


def _split(root: Path, keep: int) -> list[tuple[str, str, str]]:
    """Record the first ``keep`` documents of each big-enough category as the person's, and remove the rest.

    Returns the removed documents as ``(group, category, file name)``.
    """

    by_category: dict[tuple[str, str], list[Path]] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        parts = path.relative_to(root).parts
        if parts[0].startswith(".") or parts[0] == UNFILED or len(parts) != 3 or path.name == "kinds.json":
            continue
        by_category.setdefault((parts[0], parts[1]), []).append(path)
    held: list[tuple[str, str, str]] = []
    records: list[LedgerRecord] = []
    for (group, category), paths in by_category.items():
        if len(paths) <= keep:
            continue
        for path in paths[:keep]:
            relative = path.relative_to(root).as_posix()
            records.append(
                LedgerRecord(
                    event="filed",
                    job_id="sim",
                    path=relative,
                    original_path=f"_sorting/{path.name}",
                    content_hash=relative,
                    unit_type="file",
                    group=group,
                    category=category,
                    classified_by="user",
                )
            )
        for path in paths[keep:]:
            held.append((group, category, path.name))
            _stash(root, path)
    Ledger(root / ".microfiche").append(records)
    return held


def _stash(root: Path, path: Path) -> None:
    """Move a held-out document out of the library so learning cannot see it."""

    target = root.parent / f"{root.name}-held" / path.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(path, target)


def _enable(root: Path, min_decisions: int, max_hints: int) -> None:
    config = root / ".microfiche" / "microfiche-config.toml"
    config.write_text(
        config.read_text(encoding="utf-8")
        + f"\n[learning]\nenabled = true\nmin_decisions = {min_decisions}\nmax_hints_per_run = {max_hints}\n",
        encoding="utf-8",
    )


def _classify(root: Path, held: list[tuple[str, str, str]]) -> list[tuple[str, str] | None]:
    """What the rules file each held-out document under, or ``None`` if they hold it back."""

    library = Library(root)
    classifier = Classifier.from_library(library)
    taxonomy = library.taxonomy()
    answers: list[tuple[str, str] | None] = []
    for group, category, name in held:
        path = root.parent / f"{root.name}-held" / group / category / name
        document = read_documents([path]).documents[0]
        result = classifier.classify_document(document, taxonomy)
        answers.append(result.folders if result.confident and result.folders and len(result.folders) == 2 else None)  # type: ignore[arg-type]
    return answers


if __name__ == "__main__":
    print(report())
