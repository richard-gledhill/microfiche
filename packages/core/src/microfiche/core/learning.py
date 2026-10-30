"""Learning keyword hints from the documents a person filed by hand in ``review``.

After a ``review`` commit, and only when ``[learning] enabled`` is on, a category the person filed into may gain
``learned_hints`` in ``microfiche-library.json``: words that most of the documents the person filed there contain and that
no document filed under another category of the same group does. It is term frequency, not a model. Only the hint words
are written anywhere. The person's own hints, rules and entries are never changed (docs/development/adr/ADR-008-hint-learning.md).
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from microfiche.core.config import ConfigError
from microfiche.core.ledger import Ledger
from microfiche.core.library.library import Library
from microfiche.core.library.library_file import LIBRARY_FILENAME, FolderNode, LibraryFile, load_library_file
from microfiche.core.library.library_sync import write_library_file
from microfiche.core.models.ledger import LedgerRecord
from microfiche.core.parsers import read_documents
from microfiche.core.rules.normalise import normalise_for_matching

_logger = logging.getLogger(__name__)

# region Constants and types

# The share of a category's user-filed documents a word must appear in (and at least two documents).
_SUPPORT = 0.6
_STOPWORDS = frozenset([
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "also",
    "although",
    "always",
    "among",
    "and",
    "any",
    "are",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "can",
    "cannot",
    "could",
    "did",
    "does",
    "doing",
    "done",
    "down",
    "during",
    "each",
    "either",
    "else",
    "every",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "here",
    "hers",
    "him",
    "his",
    "how",
    "however",
    "into",
    "its",
    "itself",
    "just",
    "least",
    "less",
    "may",
    "might",
    "more",
    "most",
    "much",
    "must",
    "neither",
    "nor",
    "not",
    "now",
    "off",
    "once",
    "only",
    "onto",
    "other",
    "ought",
    "our",
    "ours",
    "out",
    "over",
    "own",
    "per",
    "same",
    "shall",
    "she",
    "should",
    "since",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "thus",
    "too",
    "under",
    "until",
    "upon",
    "very",
    "was",
    "were",
    "what",
    "when",
    "where",
    "whether",
    "which",
    "while",
    "who",
    "whom",
    "whose",
    "why",
    "will",
    "with",
    "within",
    "without",
    "would",
    "yet",
    "you",
    "your",
    "yours",
])


@dataclass(frozen=True)
class LearnedHint:
    """A keyword that was added to a category's ``learned_hints``.

    Attributes:
        group: The group folder.
        category: The category folder.
        hint: The word added.
    """

    group: str
    category: str
    hint: str


# endregion


# region Public API


def learn_hints(library: Library, categories: Iterable[tuple[str, str]], job_id: str) -> list[LearnedHint]:
    """Add hints to the categories a person just filed into, if learning is on and the evidence is strong enough.

    The evidence is every document the ledger records as filed by the person (``classified_by = "user"``) under a
    category, read from the library. A word is learned for a category when: the category has at least
    ``[learning] min_decisions`` such documents; the word is in at least 60% of them (and two); it is at least
    ``min_word_length`` letters, not a common word, not part of the group's or category's name and not already a hint;
    no document under another category of the same group contains it; and the person has not deleted it before. At most
    ``max_hints_per_run`` are added per category.

    The library file is written atomically and then each hint is recorded in the ledger (``hint_learned``), which is how
    a deleted hint is remembered. A failed write is logged and nothing is learned; it never raises. The caller holds the
    run lock.

    Args:
        library: The library the person filed into.
        categories: The ``(group, category)`` pairs the commit filed into.
        job_id: The job that filed them, recorded with each learned hint.

    Returns:
        The hints added, in a stable order; empty if learning is off or nothing qualified.
    """

    settings = library.config.learning
    if not settings.enabled:
        return []
    ledger = Ledger(library.state_dir)
    try:
        library_file = load_library_file(library.state_dir, library.config.library_structure.depth)
        current = ledger.current()
        rejected = _rejected(ledger, library_file)
    except (ConfigError, OSError, ValueError) as err:  # learning must never fail a commit
        _logger.warning("learning: skipped, could not read the library file or ledger: %s", err)
        return []

    texts = _TextCache(library)
    learned: list[LearnedHint] = []
    for group, category in sorted(set(categories)):
        mine = [r for r in current if r.group == group and r.category == category and r.classified_by == "user"]
        if len(mine) < settings.min_decisions:
            continue
        siblings = [r for r in current if r.group == group and r.category != category]
        known = _known_words(library_file, group, category) | {
            hint for g, c, hint in rejected if (g, c) == (group, category)
        }
        for word in _candidates(mine, siblings, known, texts, settings.min_word_length, settings.max_hints_per_run):
            learned.append(LearnedHint(group, category, word))
    if not learned:
        return []

    updated = _with_hints(library_file, learned)
    try:
        write_library_file(library.state_dir / LIBRARY_FILENAME, updated)
    except OSError as err:
        _logger.warning("learning: could not write %s, nothing learned: %s", LIBRARY_FILENAME, err)
        return []
    library.library_file = updated
    ledger.append(
        LedgerRecord(
            event="hint_learned",
            job_id=job_id,
            path=f"{hint.group}/{hint.category}",
            original_path="",
            content_hash="",
            unit_type="folder",
            group=hint.group,
            category=hint.category,
            hint=hint.hint,
            classified_by="learning",
        )
        for hint in learned
    )
    _logger.info("learning: added %s", ", ".join(f"'{h.hint}' to {h.group}/{h.category}" for h in learned))
    return learned


# endregion


# region Helpers


class _TextCache:
    """The set of normalised words in each ledger record's document or folder, read once."""

    def __init__(self, library: Library) -> None:
        self._library = library
        self._words: dict[str, frozenset[str]] = {}

    def words(self, record: LedgerRecord) -> frozenset[str]:
        if record.path not in self._words:
            self._words[record.path] = self._read(self._library.root / record.path)
        return self._words[record.path]

    def _read(self, path: Path) -> frozenset[str]:
        if path.is_file():
            files = [path]
        elif path.is_dir():
            files = sorted(p for p in path.rglob("*") if p.is_file())
        else:
            return frozenset()
        documents = read_documents(files, max_bytes=self._library.config.parsing.max_file_bytes).documents
        return frozenset(word for document in documents for word in normalise_for_matching(document.content).split())


def _candidates(
    mine: list[LedgerRecord],
    siblings: list[LedgerRecord],
    known: set[str],
    texts: _TextCache,
    min_length: int,
    limit: int,
) -> list[str]:
    """The words to learn for one category, best first, at most ``limit``."""

    counts: Counter[str] = Counter()
    for record in mine:
        counts.update(texts.words(record))
    needed = max(2, math.ceil(_SUPPORT * len(mine)))
    elsewhere: set[str] = set()
    for record in siblings:
        elsewhere |= texts.words(record)
    eligible = [
        word
        for word, count in counts.items()
        if count >= needed
        and len(word) >= min_length
        and word.isalpha()
        and word not in _STOPWORDS
        and word not in known
        and word not in elsewhere
    ]
    return sorted(eligible, key=lambda word: (-counts[word], -len(word), word))[:limit]


def _known_words(library_file: LibraryFile, group: str, category: str) -> set[str]:
    """Words not worth learning for ``group``/``category``: its hints, learned or not, and the words of both names."""

    hints = (*library_file.hints_for(group, category), *library_file.group_hints_for(group))
    names = (group, category)
    return {
        word for text in (*hints, *names) for word in normalise_for_matching(text, folder_name=text in names).split()
    }


def _rejected(ledger: Ledger, library_file: LibraryFile) -> set[tuple[str, str, str]]:
    """Hints learned before that are no longer among the entry's hints: the person deleted them."""

    return {
        (group, category, hint)
        for group, category, hint in ledger.learned_hints()
        if hint not in _known_words_of_hints(library_file, group, category)
    }


def _known_words_of_hints(library_file: LibraryFile, group: str, category: str) -> set[str]:
    return {word for hint in library_file.hints_for(group, category) for word in normalise_for_matching(hint).split()}


def _with_hints(library_file: LibraryFile, learned: list[LearnedHint]) -> LibraryFile:
    """``library_file`` with each hint appended to its category's ``learned_hints``, creating entries as needed."""

    groups = list(library_file.groups)
    for hint in learned:
        groups = _add(groups, (hint.group, hint.category), hint.hint)
    return library_file.model_copy(update={"groups": groups})


def _add(nodes: list[FolderNode], path: tuple[str, ...], hint: str) -> list[FolderNode]:
    """``nodes`` with ``hint`` added to the entry at ``path`` (by folder name, ignoring case), which is made if missing."""

    name, rest = path[0], path[1:]
    for index, node in enumerate(nodes):
        if node.name.casefold() == name.casefold():
            update = (
                {"children": _add(node.children, rest, hint)}
                if rest
                else {"learned_hints": [*node.learned_hints, hint]}
            )
            return [*nodes[:index], node.model_copy(update=update), *nodes[index + 1 :]]
    created = FolderNode(name=name)
    update = {"children": _add([], rest, hint)} if rest else {"learned_hints": [hint]}
    return [*nodes, created.model_copy(update=update)]


# endregion
