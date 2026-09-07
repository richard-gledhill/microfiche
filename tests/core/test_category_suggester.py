"""Tests for the deterministic category-name suggester."""

from pathlib import Path

from core.library.category_suggester import suggest_categories
from core.models.document import Document


def test_suggest_categories_ranks_by_frequency() -> None:
    documents = [
        Document(file_path=Path("a.txt"), file_name="a.txt", extension=".txt", content="invoice invoice payment"),
        Document(file_path=Path("b.txt"), file_name="b.txt", extension=".txt", content="invoice payment terms"),
    ]

    suggestions = suggest_categories(documents, top_n=2)

    names = [suggestion.name for suggestion in suggestions]
    assert "Invoice" in names
    assert "Payment" in names
