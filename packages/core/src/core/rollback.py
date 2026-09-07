"""Reverses a filing job by replaying its recorded moves in reverse."""

from __future__ import annotations

import json
from pathlib import Path

from core.models.audit_event import AuditEvent
from core.models.job import Job
from core.utils.filesystem import safe_move


def load_job(logs_dir: Path, job_id: str) -> Job:
    job_path = logs_dir / "rollback" / f"job_{job_id}.json"
    if not job_path.exists():
        raise FileNotFoundError(f"No rollback job found for id '{job_id}' at {job_path}")  # noqa: TRY003
    return Job.model_validate(json.loads(job_path.read_text(encoding="utf-8")))


def save_job(logs_dir: Path, job: Job) -> Path:
    rollback_dir = logs_dir / "rollback"
    rollback_dir.mkdir(parents=True, exist_ok=True)
    job_path = rollback_dir / f"job_{job.job_id}.json"
    job_path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return job_path


def rollback_job(logs_dir: Path, job_id: str) -> list[AuditEvent]:
    """Undo every move recorded in job ``job_id``, moving each file back to its original path."""

    job = load_job(logs_dir, job_id)
    reversed_events: list[AuditEvent] = []
    for event in reversed(job.moves):
        if event.action == "move" and event.new_path is not None:
            safe_move(event.new_path, event.original_path)
            reversed_events.append(
                AuditEvent(original_path=event.new_path, new_path=event.original_path, action="rollback")
            )
    return reversed_events
