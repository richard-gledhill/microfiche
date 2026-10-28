"""Measures how the confidence threshold trades auto-filing against misfiling, on a labelled corpus.

The corpus (``corpus/``) is a set of small libraries, one per taxonomy. A document's *truth* is simply
where it sits: ``<group>/<category>/<file>``, or ``_unfiled/<file>`` for a document that belongs to none
of the library's groups. Each library carries the ``.microfiche`` config a user of that taxonomy would
write, and a ``kinds.json`` tagging each file with why it was written (see ``ADVERSARIAL_KINDS``).

The harness classifies every document with the real pipeline - ``Library``, ``read_documents`` and
``Classifier`` with no AI fallback - then asks, for any threshold, what would have been filed
automatically, and whether that was right. Rules-only confidence doesn't depend on the threshold, so
the corpus is classified once and every threshold is evaluated against the same results.

The same harness works on any library whose files are already correctly filed: point ``load_corpus`` at
a folder whose subfolders are such libraries (see docs/development/testing/calibration.md). Files in the inbox,
in excluded folders, or loose at the top of a group are skipped; files nested below a category count as
belonging to it.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from microfiche.core.classifier import Classifier, Resolver
from microfiche.core.library.library import Library
from microfiche.core.models.unit import SortableUnit
from microfiche.core.parsers import read_documents

CORPUS_ROOT = Path(__file__).parent / "corpus"
FLAT_CORPUS_ROOT = Path(__file__).parent / "corpus_flat"  # depth-1 libraries: documents sit directly in a group
STYLES_CORPUS_ROOT = Path(__file__).parent / "corpus_styles"  # folders written in different naming styles
UNFILED = "_unfiled"
THRESHOLDS = (0.0, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0)

# Kinds written to make a name or hint match the WRONG answer. Everything else is either an ordinary
# document, or one where the right outcome is to hold it for review (nogroup, shortform).
ADVERSARIAL_KINDS = frozenset({"incidental", "incidental-hint", "hintcollision", "crossref", "shortname", "lookalike"})


@dataclass(frozen=True)
class Case:
    """One classified corpus document.

    Attributes:
        taxonomy: Which library of the corpus it belongs to.
        path: Its path inside that library, with forward slashes.
        kind: Why it was written (see the corpus module docs and ``ADVERSARIAL_KINDS``).
        truth: The (group, category) it belongs to, or ``None`` if it belongs to no group. The category is
            ``None`` in a flat library, which has none.
        predicted: What the classifier chose, ``None`` parts where it couldn't.
        confidence: The classifier's overall confidence in that choice.
        group_signal: How the group was found: ``exact``, ``fuzzy``, ``rule``, ``hint`` or ``none``. (``rule``
            and ``hint`` only in a flat library, where a group is also the destination.)
        category_signal: How the category was found: ``rule``, ``name``, ``hint`` or ``none``.
        flat: Whether the library is flat (``depth`` 1), so there is no category to resolve.
    """

    taxonomy: str
    path: str
    kind: str
    truth: tuple[str, str | None] | None
    predicted: tuple[str | None, str | None]
    confidence: float
    group_signal: str
    category_signal: str
    flat: bool = False

    @property
    def resolved(self) -> bool:
        return self.predicted[0] is not None and (self.flat or self.predicted[1] is not None)

    @property
    def correct(self) -> bool:
        return self.truth is not None and self.predicted == self.truth

    @property
    def signal(self) -> str:
        if self.flat:
            return f"group {self.group_signal}"
        return f"group {self.group_signal} / category {self.category_signal}"

    def is_filed(self, threshold: float) -> bool:
        """Whether a classifier with this threshold would file the document without asking."""

        return self.resolved and self.confidence >= threshold


@dataclass(frozen=True)
class Outcome:
    """What one threshold does to a set of cases.

    Attributes:
        threshold: The threshold evaluated.
        total: Number of cases.
        belonging: How many of them belong to some group (the most that could be filed correctly).
        filed_correct: Filed automatically, and in the right place.
        filed_wrong: Filed automatically in the wrong place - a misfile (this includes filing a document
            that belongs to no group at all).
        held_right: Held for review although the suggestion was right (a needless review).
        held_other: Held for review with no right answer on offer (wrong or no suggestion, or it belongs nowhere).
    """

    threshold: float
    total: int
    belonging: int
    filed_correct: int
    filed_wrong: int
    held_right: int
    held_other: int

    @property
    def filed(self) -> int:
        return self.filed_correct + self.filed_wrong

    @property
    def misfile_rate(self) -> float:
        """Misfiles as a share of what was filed automatically (0 if nothing was)."""

        return self.filed_wrong / self.filed if self.filed else 0.0

    @property
    def coverage(self) -> float:
        """Correct automatic filings as a share of the documents that belong somewhere."""

        return self.filed_correct / self.belonging if self.belonging else 0.0

    @property
    def misfiles_per_100(self) -> float:
        return 100 * self.filed_wrong / self.total if self.total else 0.0


def load_corpus(
    corpus_root: Path = CORPUS_ROOT, *, fallback: Resolver | None = None, threshold: float | None = None
) -> list[Case]:
    """Classify every document of every library under ``corpus_root`` with the real pipeline.

    Args:
        corpus_root: A folder whose subfolders are labelled libraries.
        fallback: An optional fallback resolver (the AI). With one, the confidence depends on the
            threshold - the fallback is only asked about answers below it - so pass ``threshold`` too.
        threshold: Overrides each library's configured confidence threshold.
    """

    cases: list[Case] = []
    for library_dir in sorted(p for p in corpus_root.iterdir() if p.is_dir()):
        library = Library(library_dir)
        taxonomy = library.taxonomy()
        if threshold is not None:
            library.config.classification.confidence_threshold = threshold
        classifier = Classifier.from_library(library, fallback)
        kinds_file = library_dir / "kinds.json"
        kinds: dict[str, str] = json.loads(kinds_file.read_text(encoding="utf-8")) if kinds_file.exists() else {}
        for path in sorted(p for p in library_dir.rglob("*") if p.is_file()):
            relative = path.relative_to(library_dir)
            parts = relative.parts
            if parts[0].startswith(".") or relative.name == "kinds.json":
                continue
            if parts[0] == UNFILED:
                truth = None
            elif library.is_excluded(path) or len(parts) < (2 if taxonomy.is_flat else 3):
                continue  # the inbox, excluded folders, and loose files are not filed documents
            else:
                # Deeper files belong to their category (or, in a flat library, to their group).
                truth = (parts[0], None if taxonomy.is_flat else parts[1])
            read = read_documents([path])
            unit = SortableUnit(source_path=path, kind="file", documents=read.documents, unreadable=read.unreadable)
            result = classifier.classify_unit(unit, taxonomy)
            cases.append(
                Case(
                    taxonomy=library_dir.name,
                    path=relative.as_posix(),
                    kind=kinds.get(relative.as_posix(), "untagged"),
                    truth=truth,
                    predicted=(result.group.name, result.category.name if result.category else None),
                    confidence=result.overall_confidence,
                    group_signal=_group_signal(result.group.reason),
                    category_signal=_category_signal(result.category.reason) if result.category else "none",
                    flat=taxonomy.is_flat,
                )
            )
    return cases


def evaluate(cases: Iterable[Case], threshold: float) -> Outcome:
    """What a classifier with ``threshold`` would do with ``cases``."""

    filed_correct = filed_wrong = held_right = held_other = total = belonging = 0
    for case in cases:
        total += 1
        belonging += case.truth is not None
        if case.is_filed(threshold):
            if case.correct:
                filed_correct += 1
            else:
                filed_wrong += 1
        elif case.correct:
            held_right += 1
        else:
            held_other += 1
    return Outcome(threshold, total, belonging, filed_correct, filed_wrong, held_right, held_other)


def sweep(cases: Sequence[Case], thresholds: Iterable[float] = THRESHOLDS) -> list[Outcome]:
    return [evaluate(cases, threshold) for threshold in thresholds]


@dataclass(frozen=True)
class Blend:
    """Per-100-document figures for one threshold, if a share of the documents were adversarial.

    The corpus over-represents tricky documents on purpose, so its raw rates say little about a real
    library. Blending the ordinary and adversarial outcomes at a chosen share shows how the trade-off
    moves with how often real documents trip the rules.

    Attributes:
        right: Documents filed automatically and correctly, per 100.
        wrong: Documents filed automatically and wrongly (misfiles), per 100.
    """

    right: float
    wrong: float


def blend(ordinary: Outcome, adversarial: Outcome, tricky_share: float) -> Blend:
    """Combine an ordinary and an adversarial outcome as if ``tricky_share`` (0-1) of documents were adversarial."""

    def per_hundred(field: str) -> float:
        parts = ((1 - tricky_share, ordinary), (tricky_share, adversarial))
        return 100 * sum(share * getattr(o, field) / o.total for share, o in parts if o.total)

    return Blend(right=per_hundred("filed_correct"), wrong=per_hundred("filed_wrong"))


def break_even(lower: Blend, higher: Blend) -> float | None:
    """How many needless reviews one avoided misfile must be worth for the higher threshold to pay off.

    ``lower`` and ``higher`` are the same documents at a lower and a higher threshold. The higher one
    files fewer documents correctly (each becomes a review) and makes fewer misfiles; this is the ratio.
    Returns ``None`` if the higher threshold avoids no misfiles at all.
    """

    avoided = lower.wrong - higher.wrong
    if avoided <= 0:
        return None
    return (lower.right - higher.right) / avoided


def by_signal(cases: Iterable[Case]) -> dict[str, list[Case]]:
    """Group the cases that produced a resolved answer by how that answer was found."""

    groups: dict[str, list[Case]] = defaultdict(list)
    for case in cases:
        if case.resolved:
            groups[case.signal].append(case)
    return dict(groups)


def by_kind(cases: Iterable[Case]) -> dict[str, list[Case]]:
    groups: dict[str, list[Case]] = defaultdict(list)
    for case in cases:
        groups[case.kind].append(case)
    return dict(groups)


def misfiles(cases: Iterable[Case], threshold: float) -> list[Case]:
    """The documents a classifier with ``threshold`` would file in the wrong place."""

    return [case for case in cases if case.is_filed(threshold) and not case.correct]


def format_report(cases: Sequence[Case], default_threshold: float) -> str:
    """A plain-text report of the corpus, every threshold, every signal, and the misfiles at the default."""

    adversarial = [c for c in cases if c.kind in ADVERSARIAL_KINDS]
    ordinary = [c for c in cases if c.kind not in ADVERSARIAL_KINDS]
    kinds = Counter(c.kind for c in cases)
    lines = [
        f"Corpus: {len(cases)} documents in {len({c.taxonomy for c in cases})} libraries; "
        f"{sum(c.truth is None for c in cases)} belong to no group; {len(adversarial)} are adversarial.",
        "Kinds: " + ", ".join(f"{kind} {count}" for kind, count in sorted(kinds.items())),
        "",
    ]
    for title, subset in (
        ("ALL DOCUMENTS", cases),
        ("ORDINARY DOCUMENTS", ordinary),
        ("ADVERSARIAL DOCUMENTS", adversarial),
    ):
        lines += [title, _threshold_table(subset, default_threshold), ""]

    lines += [
        "BY HOW THE ANSWER WAS FOUND, ordinary documents (precision = share of answers that were right)",
        _signal_table(ordinary),
        "",
        "BY HOW THE ANSWER WAS FOUND, adversarial documents",
        _signal_table(adversarial),
        "",
        "IF THIS SHARE OF YOUR DOCUMENTS WERE TRICKY (per 100 documents; right = filed correctly, wrong = misfiled)",
        _prevalence_table(ordinary, adversarial),
        "",
        f"MISFILES AT THRESHOLD {default_threshold}",
        _misfile_list(cases, default_threshold),
    ]
    return "\n".join(lines)


# region Helpers


def _threshold_table(cases: Sequence[Case], default_threshold: float) -> str:
    rows = [
        f"{'threshold':>9} {'filed':>6} {'right':>6} {'wrong':>6} {'misfile%':>9} {'coverage%':>10} {'misfiles/100':>13}"
    ]
    for outcome in sweep(cases):
        marker = " <- default" if outcome.threshold == default_threshold else ""
        rows.append(
            f"{outcome.threshold:>9.2f} {outcome.filed:>6} {outcome.filed_correct:>6} {outcome.filed_wrong:>6} "
            f"{100 * outcome.misfile_rate:>9.1f} {100 * outcome.coverage:>10.1f} {outcome.misfiles_per_100:>13.1f}{marker}"
        )
    return "\n".join(rows)


def _prevalence_table(ordinary: Sequence[Case], adversarial: Sequence[Case]) -> str:
    thresholds = (0.75, 0.8, 0.9, 0.95)
    outcomes = {t: (evaluate(ordinary, t), evaluate(adversarial, t)) for t in thresholds}
    header = (
        f"{'tricky docs':>11} | " + " | ".join(f"@{t:<4} right wrong" for t in thresholds) + " | break-even 0.75->0.8"
    )
    rows = [header]
    for share in (0.0, 0.05, 0.10, 0.20, 0.30):
        blends = {t: blend(*outcomes[t], share) for t in thresholds}
        cells = " | ".join(f"{'':5}{blends[t].right:5.1f} {blends[t].wrong:5.1f}" for t in thresholds)
        be = break_even(blends[0.75], blends[0.8])
        rows.append(f"{100 * share:>10.0f}% | {cells} | {'n/a' if be is None else f'{be:.1f} reviews per misfile'}")
    return "\n".join(rows)


def _signal_table(cases: Sequence[Case]) -> str:
    rows = [f"{'how found':<38} {'score':>6} {'docs':>5} {'right':>6} {'wrong':>6} {'precision%':>11}"]
    groups = by_signal(cases)
    for signal in sorted(groups, key=lambda s: (-max(c.confidence for c in groups[s]), s)):
        members = groups[signal]
        right = sum(c.correct for c in members)
        scores = sorted({c.confidence for c in members})
        score = f"{scores[0]:.2f}" if len(scores) == 1 else f"{scores[0]:.2f}+"
        rows.append(
            f"{signal:<38} {score:>6} {len(members):>5} {right:>6} {len(members) - right:>6} {100 * right / len(members):>11.1f}"
        )
    return "\n".join(rows)


def _misfile_list(cases: Sequence[Case], threshold: float) -> str:
    wrong = misfiles(cases, threshold)
    if not wrong:
        return "  (none)"
    return "\n".join(
        f"  {case.confidence:.2f}  {case.kind:<16} {case.taxonomy}/{case.path}  ->  {_where(case)}"
        for case in sorted(wrong, key=lambda c: (-c.confidence, c.taxonomy, c.path))
    )


def _where(case: Case) -> str:
    """Where the classifier would have filed the case, as ``group / category`` (or the group alone if flat)."""

    return " / ".join(part for part in case.predicted if part is not None) or "(unresolved)"


def _group_signal(reason: str) -> str:
    if reason.startswith("Exact match"):
        return "exact"
    if reason.startswith("Fuzzy match"):
        return "fuzzy"
    if reason.startswith("Filename matched"):
        return "rule"
    if reason.startswith("Keyword hint"):
        return "hint"
    return "none"


def _category_signal(reason: str) -> str:
    if reason.startswith("Filename matched"):
        return "rule"
    if reason.startswith("Category name"):
        return "name"
    if reason.startswith("Keyword hint"):
        return "hint"
    return "none"


# endregion
