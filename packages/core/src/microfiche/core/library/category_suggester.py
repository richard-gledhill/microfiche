"""Proposes new category folder names based on common terms across a set of documents.

Never creates folders itself - the caller (the CLI's `propose-categories` command) decides
whether to apply a suggestion. Deterministic keyword-frequency scoring only; an AI-assisted variant is designed but
not built (docs/development/architecture/overview.md, section 6).
"""

from __future__ import annotations

import itertools
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from microfiche.core.models.document import Document
from microfiche.core.rules.normalise import normalise_for_matching

# Words too common to name a category: articles, pronouns, modals, question words, prepositions, conjunctions,
# common adverbs, very common verbs and nouns. The tokenizer only yields words of three or more letters, so
# shorter ones are not listed.
STOPWORDS: frozenset[str] = frozenset({
    "able",
    "about",
    "above",
    "across",
    "after",
    "again",
    "against",
    "ago",
    "all",
    "almost",
    "along",
    "already",
    "also",
    "although",
    "always",
    "among",
    "and",
    "another",
    "any",
    "anyone",
    "anything",
    "are",
    "around",
    "bad",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "came",
    "can",
    "case",
    "cases",
    "come",
    "comes",
    "could",
    "day",
    "days",
    "dear",
    "did",
    "does",
    "doing",
    "done",
    "during",
    "each",
    "either",
    "else",
    "etc",
    "even",
    "every",
    "everyone",
    "everything",
    "few",
    "fewer",
    "find",
    "first",
    "for",
    "found",
    "from",
    "further",
    "furthermore",
    "gave",
    "get",
    "gets",
    "getting",
    "give",
    "given",
    "gives",
    "goes",
    "going",
    "gone",
    "good",
    "got",
    "great",
    "had",
    "has",
    "have",
    "having",
    "hello",
    "hence",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "however",
    "instead",
    "into",
    "its",
    "itself",
    "just",
    "know",
    "known",
    "knows",
    "last",
    "later",
    "least",
    "less",
    "let",
    "lets",
    "like",
    "likes",
    "look",
    "looking",
    "looks",
    "made",
    "make",
    "makes",
    "making",
    "many",
    "may",
    "maybe",
    "meanwhile",
    "might",
    "mine",
    "month",
    "months",
    "more",
    "moreover",
    "most",
    "much",
    "must",
    "myself",
    "need",
    "needed",
    "needs",
    "neither",
    "never",
    "new",
    "next",
    "nobody",
    "nor",
    "not",
    "nothing",
    "now",
    "number",
    "often",
    "old",
    "once",
    "one",
    "ones",
    "only",
    "onto",
    "other",
    "otherwise",
    "ought",
    "our",
    "ours",
    "ourselves",
    "over",
    "own",
    "part",
    "parts",
    "per",
    "perhaps",
    "please",
    "plus",
    "point",
    "previous",
    "put",
    "quite",
    "rather",
    "really",
    "regards",
    "said",
    "same",
    "saw",
    "say",
    "says",
    "second",
    "see",
    "seen",
    "sees",
    "set",
    "sets",
    "several",
    "shall",
    "she",
    "should",
    "since",
    "some",
    "someone",
    "something",
    "sometimes",
    "soon",
    "still",
    "such",
    "sure",
    "take",
    "taken",
    "takes",
    "taking",
    "than",
    "thank",
    "thanks",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "therefore",
    "these",
    "they",
    "thing",
    "things",
    "think",
    "thinks",
    "third",
    "this",
    "those",
    "though",
    "through",
    "thus",
    "time",
    "times",
    "today",
    "too",
    "took",
    "toward",
    "towards",
    "under",
    "unless",
    "until",
    "upon",
    "use",
    "used",
    "uses",
    "using",
    "usually",
    "very",
    "via",
    "want",
    "wants",
    "was",
    "way",
    "ways",
    "week",
    "weeks",
    "well",
    "went",
    "were",
    "what",
    "whatever",
    "when",
    "where",
    "whether",
    "which",
    "whichever",
    "while",
    "who",
    "whoever",
    "whom",
    "whose",
    "why",
    "will",
    "with",
    "within",
    "without",
    "would",
    "year",
    "years",
    "yes",
    "yet",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
})
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z-]{2,}")


@dataclass
class CategorySuggestion:
    """A candidate category name backed by supporting evidence.

    Attributes:
        name: The suggested category name.
        count: How many of the documents contain the word.
        total: How many documents were looked at, so ``count`` can be judged (7 of 12, or 7 of 400).
        example_documents: File names of up to three documents containing it.
    """

    name: str
    count: int
    total: int
    example_documents: list[str]


def suggest_categories(
    documents: list[Document], top_n: int = 5, existing_names: Iterable[str] = ()
) -> list[CategorySuggestion]:
    """Suggest up to ``top_n`` new category names from common words across ``documents``.

    Common English words (``STOPWORDS``) are never proposed, nor is a word that matches the name of a folder that
    already exists, compared as matching does (``03 Invoice`` rules out ``Invoice``).

    Args:
        documents: The documents to scan for common words.
        top_n: The most suggestions to return.
        existing_names: Names of the library's existing group and category folders.

    Returns:
        The suggestions, with the most documents first.
    """

    taken = {normalise_for_matching(name, folder_name=True) for name in existing_names}
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    for document in documents:
        words = {word.lower() for word in _WORD_RE.findall(document.content)} - STOPWORDS
        counts.update(words)
        for word in words:
            examples.setdefault(word, []).append(document.file_name)

    ranked = (item for item in counts.most_common() if normalise_for_matching(item[0], folder_name=True) not in taken)
    return [
        CategorySuggestion(name=word.title(), count=count, total=len(documents), example_documents=examples[word][:3])
        for word, count in itertools.islice(ranked, top_n)
    ]
