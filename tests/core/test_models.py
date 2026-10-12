"""Smoke tests for the pydantic models."""

from pathlib import Path

from core.models.audit_event import AuditEvent
from core.models.category import Taxonomy
from core.models.classification import CategoryMatch, ClassificationResult, GroupMatch
from core.models.document import Document
from core.models.job import Job
from core.models.ledger import LedgerRecord
from core.models.unit import SortableUnit


def test_document_round_trip() -> None:
    document = Document(file_path=Path("a/b.txt"), file_name="b.txt", extension=".txt", content="hello")
    assert document.file_name == "b.txt"


def test_taxonomy_categories_for_unknown_group_empty() -> None:
    taxonomy = Taxonomy(groups={"Phoenix": ["01 Requirements"]})
    assert taxonomy.categories_for("Atlas") == []
    assert taxonomy.categories_for("Phoenix") == ["01 Requirements"]


def test_sortable_unit_wraps_documents() -> None:
    document = Document(file_path=Path("a.txt"), file_name="a.txt", extension=".txt", content="x")
    unit = SortableUnit(source_path=Path("a.txt"), kind="file", documents=[document])
    assert unit.kind == "file"
    assert len(unit.documents) == 1


def test_ledger_record_round_trips_through_json() -> None:
    record = LedgerRecord(
        event="filed",
        job_id="job1",
        path="Project Phoenix/01 Requirements/notes.md",
        original_path="_sorting/notes.md",
        content_hash="abc123",
        unit_type="file",
        group="Project Phoenix",
        category="01 Requirements",
        group_reason="Exact match on group name 'Project Phoenix'",
        category_reason="Category name '01 Requirements' found in document text",
        confidence=0.9,
        classified_by="rules_engine",
    )

    assert LedgerRecord.model_validate_json(record.model_dump_json()) == record


def test_ledger_record_rolled_back_needs_no_classification() -> None:
    record = LedgerRecord(
        event="rolled_back",
        job_id="job1",
        path="Project Phoenix/01 Requirements/notes.md",
        original_path="_sorting/notes.md",
        content_hash="abc123",
        unit_type="file",
    )

    assert record.group is None
    assert record.confidence is None


def test_job_defaults_not_rolled_back_round_trips_json() -> None:
    job = Job(job_id="job1", moves=[AuditEvent(original_path=Path("a.txt"), new_path=Path("b/a.txt"), action="move")])

    assert job.rolled_back_at is None
    assert Job.model_validate_json(job.model_dump_json()) == job


def test_taxonomy_defaults_to_two_levels() -> None:
    taxonomy = Taxonomy(groups={"Phoenix": ["01 Requirements"]})

    assert taxonomy.depth == 2
    assert not taxonomy.is_flat


def test_taxonomy_depth_one_is_flat() -> None:
    assert Taxonomy(groups={"Household": []}, depth=1).is_flat


def _classification(
    group: str | None, category: CategoryMatch | None, *, confident: bool = True
) -> ClassificationResult:
    return ClassificationResult(
        group=GroupMatch(name=group, confidence=1.0 if group else 0.0, reason="group reason"),
        category=category,
        overall_confidence=0.9,
        classified_by="rules_engine",
        confident=confident,
    )


def _category(name: str | None) -> CategoryMatch:
    return CategoryMatch(name=name, confidence=0.9 if name else 0.0, reason="category reason")


def test_classification_folders_group_and_category() -> None:
    assert _classification("Phoenix", _category("02 Architecture")).folders == ("Phoenix", "02 Architecture")


def test_classification_folders_flat_library_is_the_group() -> None:
    assert _classification("Household", None).folders == ("Household",)


def test_classification_folders_unresolved_level_is_none() -> None:
    assert _classification(None, None).folders is None
    assert _classification("Phoenix", _category(None)).folders is None
    assert _classification(None, _category("02 Architecture")).folders is None


def test_classification_reason_is_the_deepest_levels() -> None:
    assert _classification("Phoenix", _category("02 Architecture")).reason == "category reason"
    assert _classification("Household", None).reason == "group reason"


def test_classification_held_adds_why_to_the_category_reason() -> None:
    held = _classification("Phoenix", _category("02 Architecture")).held("the name is taken")

    assert held.confident is False
    assert held.reason == "category reason; but the name is taken"
    assert held.folders == ("Phoenix", "02 Architecture")  # where it would have gone is kept


def test_classification_held_flat_library_adds_why_to_the_group_reason() -> None:
    held = _classification("Household", None).held("the name is taken")

    assert held.confident is False
    assert held.reason == "group reason; but the name is taken"
    assert held.category is None
