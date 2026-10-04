"""A single entry in the library's classification ledger."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

LedgerEvent = Literal["filed", "rolled_back"]


class LedgerRecord(BaseModel):
    """What microfiche knew about one filed unit at the moment it acted on it.

    Persisted one-per-line to ``<library>/.microfiche/ledger.jsonl``. Paths are relative to the
    library root and use forward slashes, so the ledger stays valid if the library is moved to
    another machine or OS. A unit is identified by ``(path, content_hash)``: the hash lets a
    record be found again after the file is moved or renamed outside microfiche.

    A ``"rolled_back"`` record carries only the identifying fields - the classification fields
    are ``None`` because rollback works from the job's recorded moves, not from classification.

    Attributes:
        event: ``"filed"`` when microfiche moved the unit into the library, ``"rolled_back"``
            when a rollback moved it out again.
        job_id: The job that produced this record.
        timestamp: When the record was written.
        path: Where the unit lives (``"filed"``) or lived (``"rolled_back"``) in the library.
        original_path: Where the unit was before the move that this record describes.
        content_hash: SHA-256 of the file, or of the folder's manifest for a folder unit
            (see ``core.utils.hashing.unit_hash``).
        unit_type: Whether the unit is a single file or a whole folder.
        group: The group the unit was filed under.
        category: The category the unit was filed under.
        group_reason: Why the classifier chose that group.
        category_reason: Why the classifier chose that category.
        confidence: Overall classification confidence.
        classified_by: Which classifier produced the result (e.g. ``"rules_engine"``).
    """

    event: LedgerEvent
    job_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    path: str
    original_path: str
    content_hash: str
    unit_type: Literal["file", "folder"]
    group: str | None = None
    category: str | None = None
    group_reason: str | None = None
    category_reason: str | None = None
    confidence: float | None = None
    classified_by: str | None = None
