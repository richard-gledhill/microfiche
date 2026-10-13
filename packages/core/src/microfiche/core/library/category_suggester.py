"""Proposes new category folder names based on common terms across a set of documents.

Never creates folders itself - the caller (the CLI's `propose-categories` command) decides
whether to apply a suggestion. Deterministic keyword-frequency scoring only; an AI-assisted variant is designed but
not built (docs/development/architecture.md, section 6).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from microfiche.core.models.document import Document

_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "for",
    "on",
    "with",
    "is",
    "are",
    "this",
    "that",
    "as",
    "by",
    "at",
    "be",
    "it",
    "from",
    "was",
    "were",
    "will",
    "shall",
}
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z-]{2,}")


@dataclass
class CategorySuggestion:
    """A candidate category name backed by supporting evidence.

    Attributes:
        name: The suggested category name.
        score: How many of the documents contain the word.
        example_documents: File names of up to three documents containing it.
    """

    name: str
    score: int
    example_documents: list[str]


def suggest_categories(documents: list[Document], top_n: int = 5) -> list[CategorySuggestion]:
    """Suggest up to ``top_n`` new category names from common words across ``documents``.

    Args:
        documents: The documents to scan for common words.
        top_n: The most suggestions to return.

    Returns:
        The suggestions, most common first.
    """

    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    for document in documents:
        words = {word.lower() for word in _WORD_RE.findall(document.content) if word.lower() not in _STOPWORDS}
        counts.update(words)
        for word in words:
            examples.setdefault(word, []).append(document.file_name)

    return [
        CategorySuggestion(name=word.title(), score=count, example_documents=examples[word][:3])
        for word, count in counts.most_common(top_n)
    ]
