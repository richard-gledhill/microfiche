"""Tests for the deterministic category-name suggester."""

from pathlib import Path

import pytest
from microfiche.core.library.category_suggester import STOPWORDS, suggest_categories
from microfiche.core.models.document import Document

# region Test helpers


def _doc(name: str, content: str) -> Document:
    return Document(file_path=Path(name), file_name=name, extension=".txt", content=content)


# endregion


# region suggest_categories


def test_suggest_categories_ranks_by_document_count() -> None:
    documents = [_doc("a.txt", "invoice invoice payment"), _doc("b.txt", "invoice payment terms")]

    suggestions = suggest_categories(documents, top_n=2)

    assert {suggestion.name for suggestion in suggestions} == {"Invoice", "Payment"}


def test_suggest_categories_counts_documents_not_occurrences_and_carries_total() -> None:
    documents = [_doc("a.txt", "invoice invoice invoice"), _doc("b.txt", "invoice"), _doc("c.txt", "budget")]

    invoice = suggest_categories(documents)[0]

    assert (invoice.name, invoice.count, invoice.total) == ("Invoice", 2, 3)
    assert invoice.example_documents == ["a.txt", "b.txt"]


@pytest.mark.parametrize("word", ["through", "which", "how", "can", "time", "also", "then", "they", "would"])
def test_suggest_categories_common_english_word_never_proposed(word: str) -> None:
    documents = [_doc("a.txt", f"{word} invoice"), _doc("b.txt", f"{word} invoice")]

    names = [suggestion.name.lower() for suggestion in suggest_categories(documents)]

    assert word not in names
    assert "invoice" in names


def test_stopwords_cover_the_words_a_manual_review_found() -> None:
    assert {"through", "which", "how", "can", "time", "also", "then"} <= STOPWORDS


def test_suggest_categories_existing_folder_name_dropped_under_normalisation() -> None:
    documents = [_doc("a.txt", "invoice budget"), _doc("b.txt", "invoice budget")]

    names = [s.name for s in suggest_categories(documents, existing_names=["03 Invoice", "Project Phoenix"])]

    assert names == ["Budget"]


def test_suggest_categories_existing_name_does_not_use_up_a_slot() -> None:
    documents = [_doc("a.txt", "alpha beta gamma"), _doc("b.txt", "alpha beta gamma")]

    names = [s.name for s in suggest_categories(documents, top_n=2, existing_names=["Alpha"])]

    assert len(names) == 2
    assert "Alpha" not in names


def test_suggest_categories_no_documents_gives_nothing() -> None:
    assert suggest_categories([]) == []


# endregion
