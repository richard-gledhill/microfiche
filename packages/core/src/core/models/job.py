"""A rollback job: the set of moves made by one `sort`/`resort --apply` run."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from core.models.audit_event import AuditEvent


class Job(BaseModel):
    """Everything needed to undo one run. Persisted to ``<library>/.microfiche-logs/rollback/job_<id>.json``."""

    job_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    moves: list[AuditEvent] = Field(default_factory=list)
