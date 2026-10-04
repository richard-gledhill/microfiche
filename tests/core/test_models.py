"""Smoke tests for the pydantic models."""

from pathlib import Path

from core.models.audit_event import AuditEvent
from core.models.category import Taxonomy
from core.models.document import Document
from core.models.job import Job
from core.models.ledger import LedgerRecord
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


def test_rolled_back_ledger_record_needs_no_classification_fields() -> None:
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


def test_job_is_not_rolled_back_by_default_and_round_trips_through_json() -> None:
    job = Job(job_id="job1", moves=[AuditEvent(original_path=Path("a.txt"), new_path=Path("b/a.txt"), action="move")])

    assert job.rolled_back_at is None
    assert Job.model_validate_json(job.model_dump_json()) == job
