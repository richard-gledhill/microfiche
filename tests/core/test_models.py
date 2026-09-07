"""Smoke tests for the pydantic models."""

from pathlib import Path

from core.models.category import Taxonomy
from core.models.document import Document
from core.models.unit import SortableUnit


def test_document_round_trip() -> None:
    document = Document(file_path=Path("a/b.txt"), file_name="b.txt", extension=".txt", content="hello")
    assert document.file_name == "b.txt"


def test_taxonomy_categories_for_unknown_group_returns_empty_list() -> None:
    taxonomy = Taxonomy(groups={"Phoenix": ["01 Requirements"]})
    assert taxonomy.categories_for("Atlas") == []
    assert taxonomy.categories_for("Phoenix") == ["01 Requirements"]


def test_sortable_unit_wraps_documents() -> None:
    document = Document(file_path=Path("a.txt"), file_name="a.txt", extension=".txt", content="x")
    unit = SortableUnit(source_path=Path("a.txt"), kind="file", documents=[document])
    assert unit.kind == "file"
    assert len(unit.documents) == 1
